#import <Metal/Metal.h>
#import <Foundation/Foundation.h>
#include <assert.h>
#include "../third_party/nxnative/dm/gfx/nvn/nvn_uniform_forward.h"

int main(void) { @autoreleasepool {
    uf_plan p={0};
    assert(uf_slot(&p,UINT64_MAX-1,4)<0);
    assert(uf_put(&p,(uf_version){0x1000,16,0,0,NULL}));
    assert(uf_slot(&p,0x1008,16)<0); // Overlapping partial update must flush.
    assert(uf_hits(&p,0x100f,2));assert(!uf_hits(&p,0x1010,1));
    assert(uf_find(&p,0x1004,8));assert(!uf_find(&p,0xfff,16));
    const uf_attachment attachments[9]={{10,0x4000,0x100},{0},{0},{0},{0},{0},{0},{0},{20,0x8000,0x100}};
    assert(uf_attachment_dependencies((uf_attachment){10,0x4000,0x100},attachments,9,0)==0); // No preceding write.
    assert(uf_attachment_dependencies((uf_attachment){10,0x4000,0x100},attachments,9,1)==1);
    assert(uf_attachment_dependencies((uf_attachment){21,0x8080,0x40},attachments,9,256)==256); // Aliased depth view, different serial.
    assert(uf_attachment_dependencies((uf_attachment){21,0x8100,0x40},attachments,9,256)==0); // Disjoint storage.
    assert(uf_attachment_dependencies((uf_attachment){20,0,0},attachments,9,256)==256); // Host-only same serial.
    assert(uf_attachment_dependencies((uf_attachment){99,0,0},attachments,9,256)==0);
    assert(uf_attachment_dependencies((uf_attachment){21,0x8080,0},attachments,9,256)==256); // Unknown extent must not prove safe.
    assert(uf_attachment_dependencies((uf_attachment){21,UINT64_MAX-1,8},attachments,9,256)==256);
    id<MTLDevice> device=MTLCreateSystemDefaultDevice(); assert(device);
    NSError *err=nil;
    NSString *source=@"#include <metal_stdlib>\nusing namespace metal;\n"
      "vertex float4 vertex_main(uint i [[vertex_id]]) {float2 p[3]={float2(-1,-1),float2(3,-1),float2(-1,3)};return float4(p[i],0,1);}\n"
      "fragment float4 fragment_main(constant uint4 &c [[buffer(0)]]) {return float4(c)/255.0;}\n";
    id<MTLLibrary> lib=[device newLibraryWithSource:source options:nil error:&err];assert(lib);
    MTLRenderPipelineDescriptor *desc=[MTLRenderPipelineDescriptor new];
    desc.vertexFunction=[lib newFunctionWithName:@"vertex_main"];desc.fragmentFunction=[lib newFunctionWithName:@"fragment_main"];
    desc.colorAttachments[0].pixelFormat=MTLPixelFormatRGBA8Unorm;
    id<MTLRenderPipelineState> ps=[device newRenderPipelineStateWithDescriptor:desc error:&err];assert(ps);
    MTLTextureDescriptor *td=[MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm width:64 height:1 mipmapped:NO];
    td.storageMode=MTLStorageModeShared;td.usage=MTLTextureUsageRenderTarget;
    id<MTLTexture> target=[device newTextureWithDescriptor:td];assert(target);
    id<MTLCommandQueue> q=[device newCommandQueue]; id<MTLCommandBuffer> cb=[q commandBuffer];
    MTLRenderPassDescriptor *rp=[MTLRenderPassDescriptor renderPassDescriptor];rp.colorAttachments[0].texture=target;
    rp.colorAttachments[0].loadAction=MTLLoadActionClear;rp.colorAttachments[0].storeAction=MTLStoreActionStore;
    id<MTLRenderCommandEncoder> enc=[cb renderCommandEncoderWithDescriptor:rp];[enc setRenderPipelineState:ps];
    NSMutableArray *keep=[NSMutableArray new];
    const uint32_t colors[8][4]={{255,0,0,255},{0,255,0,255},{0,0,255,255},{255,255,0,255},{255,0,255,255},{0,255,255,255},{255,255,255,255},{0,0,0,255}};
    memset(&p,0,sizeof p);
    for(unsigned i=0;i<8;i++) {
        id<MTLBuffer> b=[device newBufferWithBytes:colors[i] length:16 options:MTLResourceStorageModeShared];[keep addObject:b];
        assert(uf_put(&p,(uf_version){0x1000,16,0,b.gpuAddress,(__bridge void*)b}));
        const uf_version *v=uf_find(&p,0x1000,16);assert(v && v->gpu==b.gpuAddress);
        [enc setFragmentBuffer:(__bridge id<MTLBuffer>)v->buffer offset:v->offset atIndex:0];
        [enc setScissorRect:(MTLScissorRect){i*8,0,8,1}];[enc drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3];
    }
    [enc endEncoding];[cb commit];[cb waitUntilCompleted];assert(cb.status==MTLCommandBufferStatusCompleted);
    uint8_t pixels[64*4];[target getBytes:pixels bytesPerRow:256 fromRegion:MTLRegionMake2D(0,0,64,1) mipmapLevel:0];
    for(unsigned x=0;x<64;x++)for(unsigned c=0;c<4;c++)assert(pixels[x*4+c]==colors[x/8][c]);
    assert(p.n==1); // Latest guest write can be coalesced; eight prior bindings remain immutable.
    puts("PASS: uniform versions, overlap/overflow refusal, 64 independent expected GPU pixels in one pass");
} return 0; }
