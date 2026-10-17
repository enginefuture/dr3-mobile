// Real production MetalFX: M4 producer -> classic upscale -> M4 consumer.
// No game process, window, screenshot or controller input is involved.
#import <Metal/Metal.h>
#import <MetalFX/MetalFX.h>
#include <assert.h>
#include <stdio.h>
#include "../third_party/nxnative/dm/gfx/nvn/nvn_metalfx_spatial.h"

int main(void) { @autoreleasepool {
    id<MTLDevice> device=MTLCreateSystemDefaultDevice();assert(device);
    if(![MTLFXSpatialScalerDescriptor supportsDevice:device]){puts("SKIP: real MetalFX Spatial unavailable on this GPU");return 77;}
    NSError *error=nil;id<MTLCommandQueue> queue=[device newCommandQueue];
    id<MTL4CommandQueue> queue4=[device newMTL4CommandQueueWithDescriptor:[MTL4CommandQueueDescriptor new] error:&error];assert(queue4);
    id<MTLResidencySet> resident=[device newResidencySetWithDescriptor:[MTLResidencySetDescriptor new] error:&error];assert(resident);
    [resident requestResidency];[queue4 addResidencySet:resident];
    NVNSpatialUpscaler *upscaler=[[NVNSpatialUpscaler alloc] initWithDevice:device queue:queue queue4:queue4
      resourceAdd:^(id<MTLResource> r){[resident addAllocation:r];} resourceRemove:^(id<MTLResource> r){[resident removeAllocation:r];} resourceCommit:^{[resident commit];}];assert(upscaler);
    const NSUInteger sw=1640,sh=760;nvn_fx_rect crop={32,20,1568,720};
    MTLTextureDescriptor *td=[MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm_sRGB width:sw height:sh mipmapped:NO];
    td.storageMode=MTLStorageModePrivate;td.usage=MTLTextureUsageShaderRead|MTLTextureUsagePixelFormatView;
    id<MTLTexture> source=[device newTextureWithDescriptor:td];assert(source);
    id<MTLTexture> raw=[source newTextureViewWithPixelFormat:MTLPixelFormatRGBA8Unorm];assert(raw);
    id<MTLBuffer> staging=[device newBufferWithLength:sw*sh*4 options:MTLResourceStorageModeShared];
    id<MTLBuffer> readback=[device newBufferWithLength:2560*1176*4 options:MTLResourceStorageModeShared];assert(staging && readback);
    [resident addAllocation:source];[resident addAllocation:raw];[resident addAllocation:staging];[resident addAllocation:readback];[resident commit];
    id<MTL4CommandAllocator> producerAllocator=[device newCommandAllocatorWithDescriptor:[MTL4CommandAllocatorDescriptor new] error:&error];
    id<MTL4CommandAllocator> consumerAllocator=[device newCommandAllocatorWithDescriptor:[MTL4CommandAllocatorDescriptor new] error:&error];assert(producerAllocator && consumerAllocator);
    id<MTL4CommandBuffer> producer=[device newCommandBuffer],consumer=[device newCommandBuffer];
    id<MTLSharedEvent> producerGate=[device newSharedEvent];assert(producerGate);
    const uint8_t levels[]={0,32,64,128,192,255};unsigned checks=0;
    for(unsigned frame=0;frame<7;frame++) {
        uint8_t *pixels=staging.contents;
        for(NSUInteger y=0;y<sh;y++)for(NSUInteger x=0;x<sw;x++) {
            NSUInteger p=(y*sw+x)*4;pixels[p]=255;pixels[p+1]=0;pixels[p+2]=255;pixels[p+3]=255;
            if(x>=crop.x && x<crop.x+crop.width && y>=crop.y && y<crop.y+crop.height) {
                unsigned band=(unsigned)((x-crop.x)*6/crop.width),half=(y-crop.y)>=crop.height/2;
                for(unsigned c=0;c<3;c++)pixels[p+c]=levels[(band+frame+half+2*c)%6];
            }
        }
        [producerAllocator reset];[producer beginCommandBufferWithAllocator:producerAllocator];
        id<MTL4ComputeCommandEncoder> write=[producer computeCommandEncoder];
        [write copyFromBuffer:staging sourceOffset:0 sourceBytesPerRow:sw*4 sourceBytesPerImage:sw*sh*4 sourceSize:MTLSizeMake(sw,sh,1) toTexture:source destinationSlice:0 destinationLevel:0 destinationOrigin:MTLOriginMake(0,0,0)];
        [write endEncoding];[producer endCommandBuffer];
        [queue4 waitForEvent:producerGate value:frame+1];
        id<MTL4CommandBuffer> producers[]={producer};[queue4 commit:producers count:1];
        NSUInteger canvasWidth=frame<3?2560:2048,canvasHeight=frame<3?1176:frame<6?940:1152;
        NSUInteger expectedHeight=frame<3?1176:940;
        id<MTLTexture> output=[upscaler encodeSource:raw crop:crop canvasWidth:canvasWidth canvasHeight:canvasHeight slot:frame%3 error:&error];
        if(!output)fprintf(stderr,"%s\n",error.localizedDescription.UTF8String);assert(output);
        // Delay the real producer after MetalFX is submitted. A missing bridge
        // would sample uninitialized/previous-frame pixels on the legacy queue.
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW,5*NSEC_PER_MSEC),dispatch_get_global_queue(QOS_CLASS_DEFAULT,0),^{producerGate.signaledValue=frame+1;});
        assert(output.width==canvasWidth && output.height==expectedHeight && output.storageMode==MTLStorageModePrivate);
        NSDictionary *d=[upscaler diagnosticsForSlot:frame%3];
        assert([d[@"input_width"] unsignedIntegerValue]==1568 && [d[@"input_height"] unsignedIntegerValue]==720);
        assert([d[@"color_mode"] intValue]==MTLFXSpatialScalerColorProcessingModePerceptual);
        assert(([d[@"input_usage"] unsignedIntegerValue]&[d[@"required_input_usage"] unsignedIntegerValue])==[d[@"required_input_usage"] unsignedIntegerValue]);
        assert(([d[@"output_usage"] unsignedIntegerValue]&[d[@"required_output_usage"] unsignedIntegerValue])==[d[@"required_output_usage"] unsignedIntegerValue]);
        [consumerAllocator reset];[consumer beginCommandBufferWithAllocator:consumerAllocator];
        id<MTL4ComputeCommandEncoder> read=[consumer computeCommandEncoder];
        [read barrierAfterQueueStages:MTLStageAll beforeStages:MTLStageAll visibilityOptions:MTL4VisibilityOptionDevice];
        [read copyFromTexture:output sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0,0,0) sourceSize:MTLSizeMake(output.width,output.height,1) toBuffer:readback destinationOffset:0 destinationBytesPerRow:output.width*4 destinationBytesPerImage:output.width*output.height*4];
        [read endEncoding];[consumer endCommandBuffer];dispatch_semaphore_t done=dispatch_semaphore_create(0);
        MTL4CommitOptions *options=[MTL4CommitOptions new];[options addFeedbackHandler:^(id<MTL4CommitFeedback> feedback){assert(!feedback.error);dispatch_semaphore_signal(done);}];
        id<MTL4CommandBuffer> consumers[]={consumer};[queue4 commit:consumers count:1 options:options];
        assert(dispatch_semaphore_wait(done,dispatch_time(DISPATCH_TIME_NOW,10*NSEC_PER_SEC))==0);
        const uint8_t *actual=readback.contents;
        for(unsigned half=0;half<2;half++)for(unsigned band=0;band<6;band++)for(unsigned c=0;c<3;c++) {
            NSUInteger x=(2*band+1)*output.width/12,y=(2*half+1)*output.height/4;
            unsigned expected=levels[(band+frame+half+2*(2-c))%6]; // output BGRA vs source RGBA
            int got=actual[(y*output.width+x)*4+c];
            if(abs(got-(int)expected)>3)fprintf(stderr,"frame%u band%u half%u channel%u got=%d expected=%u\n",frame,band,half,c,got,expected);
            assert(abs(got-(int)expected)<=3);checks++;
        }
        for(NSUInteger y=1;y<output.height;y+=output.height-2)for(NSUInteger x=1;x<output.width;x+=output.width-2) {
            unsigned band=x<output.width/2?0:5,half=y>=output.height/2;
            for(unsigned c=0;c<3;c++){unsigned expected=levels[(band+frame+half+2*(2-c))%6];assert(abs((int)actual[(y*output.width+x)*4+c]-(int)expected)<=3);checks++;}
            assert(actual[(y*output.width+x)*4+3]>=250);
        }
    }
    assert((![upscaler encodeSource:raw crop:(nvn_fx_rect){sw,0,1,1} canvasWidth:2048 canvasHeight:940 slot:0 error:&error]));
    assert(![upscaler encodeSource:raw crop:crop canvasWidth:1000 canvasHeight:400 slot:0 error:&error]);
    assert(![upscaler encodeSource:source crop:crop canvasWidth:2048 canvasHeight:940 slot:0 error:&error]); // sRGB must be viewed as raw Unorm first
    printf("PASS: real MetalFX, 1568x720 -> 2560x1176 / 2048x940, 3-slot resize/reuse, cropped sentinel exclusion, perceptual RGB/order, M4 event bridge, %u independent channel checks\n",checks);
}return 0;}
