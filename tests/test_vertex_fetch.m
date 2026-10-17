// Independent expected register bits, real Metal fetch, and known D3 PSO failures.
#import <Metal/Metal.h>
#import <Foundation/Foundation.h>
#include <assert.h>
#include <stdio.h>
#include "../third_party/nxnative/dm/gfx/nvn/nvn_vertex_fetch.h"

static id<MTLDevice> device;
static id<MTLLibrary> compile(NSString *source) {
    NSError *error=nil;id<MTLLibrary> lib=[device newLibraryWithSource:source options:nil error:&error];
    if(!lib)fprintf(stderr,"%s\n",error.localizedDescription.UTF8String);assert(lib);return lib;
}
static void fetch_case(NSString *original,unsigned desired,MTLVertexFormat format,const void *data,size_t bytes,const uint32_t expected[4]) {
    NSString *source=[NSString stringWithFormat:@"#include <metal_stdlib>\nusing namespace metal;\n"
      "struct main0_in { %@4 a [[attribute(3)]]; };\n"
      "struct main0_out {float4 pos [[position]];uint4 bits [[user(locn0),flat]];};\n"
      "vertex main0_out main0(main0_in in [[stage_in]],uint id [[vertex_id]]) {\n"
      " main0_out out;float2 p[3]={float2(-1,-1),float2(3,-1),float2(-1,3)};out.pos=float4(p[id],0,1);out.bits=as_type<uint4>(in.a);return out;}\n"
      "fragment uint4 frag(main0_out in [[stage_in]]){return in.bits;}\n",original];
    unsigned originalType=[original isEqual:@"float"]?0:[original isEqual:@"uint"]?1:2;
    uint64_t signature=desired==originalType?0:nvn_vertex_fetch_set(0,3,desired);
    NSString *why=nil,*adapted=nvn_vertex_fetch_adapt(source,signature,&why);assert(adapted);
    id<MTLLibrary> lib=compile(adapted);NSError *error=nil;
    MTLRenderPipelineDescriptor *pd=[MTLRenderPipelineDescriptor new];
    pd.vertexFunction=[lib newFunctionWithName:@"main0"];pd.fragmentFunction=[lib newFunctionWithName:@"frag"];
    pd.colorAttachments[0].pixelFormat=MTLPixelFormatRGBA32Uint;
    MTLVertexDescriptor *vd=[MTLVertexDescriptor vertexDescriptor];vd.attributes[3].format=format;
    vd.attributes[3].bufferIndex=1;vd.layouts[1].stride=bytes;vd.layouts[1].stepFunction=MTLVertexStepFunctionConstant;vd.layouts[1].stepRate=0;
    pd.vertexDescriptor=vd;id<MTLRenderPipelineState> pipeline=[device newRenderPipelineStateWithDescriptor:pd error:&error];
    if(!pipeline)fprintf(stderr,"%s\n",error.localizedDescription.UTF8String);assert(pipeline);
    MTLTextureDescriptor *td=[MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA32Uint width:4 height:1 mipmapped:NO];
    td.storageMode=MTLStorageModeShared;td.usage=MTLTextureUsageRenderTarget;
    id<MTLTexture> tex=[device newTextureWithDescriptor:td];assert(tex);
    id<MTLBuffer> input=[device newBufferWithBytes:data length:bytes options:MTLResourceStorageModeShared];
    id<MTLCommandQueue> queue=[device newCommandQueue];id<MTLCommandBuffer> cb=[queue commandBuffer];
    MTLRenderPassDescriptor *rp=[MTLRenderPassDescriptor renderPassDescriptor];rp.colorAttachments[0].texture=tex;
    rp.colorAttachments[0].loadAction=MTLLoadActionClear;rp.colorAttachments[0].storeAction=MTLStoreActionStore;
    id<MTLRenderCommandEncoder> enc=[cb renderCommandEncoderWithDescriptor:rp];[enc setRenderPipelineState:pipeline];
    [enc setVertexBuffer:input offset:0 atIndex:1];[enc drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3];
    [enc endEncoding];[cb commit];[cb waitUntilCompleted];assert(cb.status==MTLCommandBufferStatusCompleted);
    uint32_t actual[16];[tex getBytes:actual bytesPerRow:sizeof actual fromRegion:MTLRegionMake2D(0,0,4,1) mipmapLevel:0];
    for(int p=0;p<4;p++)for(int c=0;c<4;c++) {
        if(actual[p*4+c]!=expected[c])fprintf(stderr,"fetch %s mode=%u pixel=%d channel=%d got=%08x expected=%08x\n",original.UTF8String,desired,p,c,actual[p*4+c],expected[c]);
        assert(actual[p*4+c]==expected[c]);
    }
}

static void known_pipeline(NSString *cache,NSString *vertex,NSString *fragment,unsigned location,MTLVertexFormat format) {
    NSString *stem=[cache stringByAppendingPathComponent:vertex];
    NSString *source=[NSString stringWithContentsOfFile:[stem stringByAppendingString:@".metal"] encoding:NSUTF8StringEncoding error:nil];assert(source);
    NSData *meta=[NSData dataWithContentsOfFile:[stem stringByAppendingString:@".json"]];
    NSDictionary *metadata=[NSJSONSerialization JSONObjectWithData:meta options:0 error:nil];
    NSString *why=nil,*adapted=nvn_vertex_fetch_adapt(source,nvn_vertex_fetch_set(0,location,NVN_FETCH_FLOAT),&why);assert(adapted);
    id<MTLLibrary> vl=compile(adapted);NSError *error=nil;
    id<MTLLibrary> fl=[device newLibraryWithURL:[NSURL fileURLWithPath:[[cache stringByAppendingPathComponent:fragment] stringByAppendingString:@".metallib"]] error:&error];assert(fl);
    MTLRenderPipelineDescriptor *pd=[MTLRenderPipelineDescriptor new];pd.vertexFunction=[vl newFunctionWithName:@"main0"];pd.fragmentFunction=[fl newFunctionWithName:@"main0"];
    pd.colorAttachments[0].pixelFormat=MTLPixelFormatRGBA8Unorm;MTLVertexDescriptor *vd=[MTLVertexDescriptor vertexDescriptor];
    for(NSDictionary *attribute in metadata[@"vertex_inputs"]) {
        NSUInteger loc=[attribute[@"location"] unsignedIntegerValue];NSString *type=attribute[@"msl_type"];
        vd.attributes[loc].format=loc==location?format:[type hasPrefix:@"uint"]?MTLVertexFormatUInt4:[type hasPrefix:@"int"]?MTLVertexFormatInt4:MTLVertexFormatFloat4;
        vd.attributes[loc].bufferIndex=1;vd.layouts[1].stride=16;
    }
    pd.vertexDescriptor=vd;id<MTLRenderPipelineState> result=[device newRenderPipelineStateWithDescriptor:pd error:&error];
    if(!result)fprintf(stderr,"real pair %s/%s: %s\n",vertex.UTF8String,fragment.UTF8String,error.localizedDescription.UTF8String);assert(result);
    NSString *prebuilt=[NSString stringWithFormat:@"%@/%@_vf%016llx.metallib",cache,vertex,(unsigned long long)nvn_vertex_fetch_set(0,location,NVN_FETCH_FLOAT)];
    if([NSFileManager.defaultManager fileExistsAtPath:prebuilt]) {
        id<MTLLibrary> packaged=[device newLibraryWithURL:[NSURL fileURLWithPath:prebuilt] error:&error];assert(packaged);
        pd.vertexFunction=[packaged newFunctionWithName:@"main0"];
        assert([device newRenderPipelineStateWithDescriptor:pd error:&error]);
    }
    // Prove the unadapted shader fails with precisely the same normalized format.
    pd.vertexFunction=[compile(source) newFunctionWithName:@"main0"];
    assert(![device newRenderPipelineStateWithDescriptor:pd error:&error]);
    printf("PASS: real D3 PSO %s / %s normalized attribute %u (negative control rejects original)\n",vertex.UTF8String,fragment.UTF8String,location);
}

int main(int argc,const char **argv) { @autoreleasepool {
    device=MTLCreateSystemDefaultDevice();assert(device);
    uint8_t unorm[4]={0,64,128,255};uint32_t unormBits[4]={0,0x3e808081,0x3f008081,0x3f800000};
    fetch_case(@"uint",0,MTLVertexFormatUChar4Normalized,unorm,sizeof unorm,unormBits);
    int16_t snorm[4]={-32768,16384,32767,-16384};uint32_t snormBits[4]={0xbf800000,0x3f000100,0x3f800000,0xbf000100};
    fetch_case(@"uint",0,MTLVertexFormatShort4Normalized,snorm,sizeof snorm,snormBits);
    uint16_t half[4]={0,0x3c00,0xbc00,0x4000};uint32_t floatBits[4]={0,0x3f800000,0xbf800000,0x40000000};
    fetch_case(@"uint",0,MTLVertexFormatHalf4,half,sizeof half,floatBits);
    uint8_t bytes[4]={0,127,128,255};uint32_t byteBits[4]={0,127,128,255};
    fetch_case(@"float",1,MTLVertexFormatUChar4,bytes,sizeof bytes,byteBits);
    int8_t signedBytes[4]={-128,-1,0,127};uint32_t signedBits[4]={0xffffff80,0xffffffff,0,127};
    fetch_case(@"uint",2,MTLVertexFormatChar4,signedBytes,sizeof signedBytes,signedBits);
    uint32_t floatSpecialBits[4]={0x7fc01234,0x80000000,0x7f800000,1};
    fetch_case(@"int",0,MTLVertexFormatFloat4,floatSpecialBits,sizeof floatSpecialBits,floatSpecialBits);
    uint32_t integers[4]={0,0xffffffff,0x3f800000,7};fetch_case(@"float",1,MTLVertexFormatUInt4,integers,sizeof integers,integers);
    fetch_case(@"uint",1,MTLVertexFormatUChar4,bytes,sizeof bytes,byteBits);
    NSString *why=nil;assert(!nvn_vertex_fetch_adapt(@"bad",1,&why));
    assert(nvn_vertex_fetch_type(0x25)==0 && nvn_vertex_fetch_type(0x2b)==0 && nvn_vertex_fetch_type(0x27)==1 && nvn_vertex_fetch_type(0x28)==2);
    if(argc>1) {
        NSString *cache=@(argv[1]);
        known_pipeline(cache,@"18f2aadcec113d49_b",@"956e6fc2fe006646_b",2,MTLVertexFormatUChar4Normalized);
        known_pipeline(cache,@"18f2aadcec113d49_b",@"22e0cb8cba3b1d5a_b",2,MTLVertexFormatUChar4Normalized);
        known_pipeline(cache,@"88ba806f61d19fae_b",@"703334b99e32841e_b",1,MTLVertexFormatShort4Normalized);
    }
    puts("PASS: vertex fetch preserves all 128 expected GPU register channels across 8 normalized/half/integer/signedness cases");
}return 0;}
