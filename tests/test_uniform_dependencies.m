// Independent expected pixels: a depth-writing draw followed by a depth reader
// with unchanged attachments must not rely on an elided uniform-copy boundary.
#import <Metal/Metal.h>
#import <Foundation/Foundation.h>
#include <assert.h>
#include "../third_party/nxnative/dm/gfx/nvn/nvn_uniform_forward.h"

int main(void) { @autoreleasepool {
    id<MTLDevice> device=MTLCreateSystemDefaultDevice();assert(device);
    NSError *error=nil;
    NSString *source=@"#include <metal_stdlib>\nusing namespace metal;\n"
      "vertex float4 vert(uint i [[vertex_id]]) {float2 p[3]={float2(-1,-1),float2(3,-1),float2(-1,3)};return float4(p[i],0.25,1);}\n"
      "fragment float4 write_depth() {return float4(1,0,0,1);}\n"
      "fragment float4 read_depth(depth2d<float> d [[texture(0)]],sampler s [[sampler(0)]]) {return float4(d.sample(s,float2(0.5)),0.5,0.75,1);}\n";
    id<MTLLibrary> library=[device newLibraryWithSource:source options:nil error:&error];assert(library);
    MTLRenderPipelineDescriptor *pipeline=[MTLRenderPipelineDescriptor new];
    pipeline.vertexFunction=[library newFunctionWithName:@"vert"];
    pipeline.fragmentFunction=[library newFunctionWithName:@"write_depth"];
    pipeline.colorAttachments[0].pixelFormat=MTLPixelFormatRGBA8Unorm;
    pipeline.colorAttachments[0].writeMask=MTLColorWriteMaskNone;
    pipeline.depthAttachmentPixelFormat=MTLPixelFormatDepth32Float;
    id<MTLRenderPipelineState> writer=[device newRenderPipelineStateWithDescriptor:pipeline error:&error];assert(writer);
    pipeline.fragmentFunction=[library newFunctionWithName:@"read_depth"];
    pipeline.colorAttachments[0].writeMask=MTLColorWriteMaskAll;
    id<MTLRenderPipelineState> reader=[device newRenderPipelineStateWithDescriptor:pipeline error:&error];assert(reader);
    MTLTextureDescriptor *td=[MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm width:64 height:1 mipmapped:NO];
    td.storageMode=MTLStorageModeShared;td.usage=MTLTextureUsageRenderTarget;
    id<MTLTexture> color=[device newTextureWithDescriptor:td];assert(color);
    td.pixelFormat=MTLPixelFormatDepth32Float;td.storageMode=MTLStorageModePrivate;
    td.usage=MTLTextureUsageRenderTarget|MTLTextureUsageShaderRead;
    id<MTLTexture> depth=[device newTextureWithDescriptor:td];assert(depth);
    MTLDepthStencilDescriptor *ds=[MTLDepthStencilDescriptor new];
    ds.depthCompareFunction=MTLCompareFunctionAlways;ds.depthWriteEnabled=YES;
    id<MTLDepthStencilState> depth_write=[device newDepthStencilStateWithDescriptor:ds];
    ds.depthWriteEnabled=NO;id<MTLDepthStencilState> depth_read=[device newDepthStencilStateWithDescriptor:ds];
    MTLSamplerDescriptor *sd=[MTLSamplerDescriptor new];
    sd.minFilter=sd.magFilter=MTLSamplerMinMagFilterNearest;
    id<MTLSamplerState> sampler=[device newSamplerStateWithDescriptor:sd];assert(sampler);
    id<MTLCommandQueue> queue=[device newCommandQueue];id<MTLCommandBuffer> cb=[queue commandBuffer];
    MTLRenderPassDescriptor *rp=[MTLRenderPassDescriptor renderPassDescriptor];
    rp.colorAttachments[0].texture=color;rp.colorAttachments[0].loadAction=MTLLoadActionClear;
    rp.colorAttachments[0].storeAction=MTLStoreActionStore;
    rp.depthAttachment.texture=depth;rp.depthAttachment.loadAction=MTLLoadActionClear;
    rp.depthAttachment.storeAction=MTLStoreActionStore;rp.depthAttachment.clearDepth=1;
    id<MTLRenderCommandEncoder> enc=[cb renderCommandEncoderWithDescriptor:rp];
    [enc setRenderPipelineState:writer];[enc setDepthStencilState:depth_write];
    [enc drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3];
    uf_attachment attachments[9]={0};attachments[8]=(uf_attachment){42,0,0};
    assert(uf_attachment_dependencies((uf_attachment){42,0,0},attachments,9,1)==0); // Color-only writes need no depth boundary.
    unsigned dependency=uf_attachment_dependencies((uf_attachment){42,0,0},attachments,9,256);
    assert(dependency==256);
    if(dependency) {
        [enc endEncoding];rp.colorAttachments[0].loadAction=MTLLoadActionLoad;
        rp.depthAttachment.loadAction=MTLLoadActionLoad;
        enc=[cb renderCommandEncoderWithDescriptor:rp];
    }
    [enc setRenderPipelineState:reader];[enc setDepthStencilState:depth_read];
    [enc setFragmentTexture:depth atIndex:0];[enc setFragmentSamplerState:sampler atIndex:0];
    [enc drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3];
    [enc endEncoding];[cb commit];[cb waitUntilCompleted];assert(cb.status==MTLCommandBufferStatusCompleted);
    uint8_t pixels[256];[color getBytes:pixels bytesPerRow:256 fromRegion:MTLRegionMake2D(0,0,64,1) mipmapLevel:0];
    for(unsigned x=0;x<64;x++){assert(pixels[x*4]==64);assert(pixels[x*4+1]==128);assert(pixels[x*4+2]==191);assert(pixels[x*4+3]==255);}
    puts("PASS: written-depth sampling boundary, no split for unrelated color writes, 64 expected GPU pixels");
}return 0;}
