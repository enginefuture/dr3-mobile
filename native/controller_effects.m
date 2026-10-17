// Core Haptics controller output, shared by Mac and iOS. The two NVN bands are
// translated to intensity/sharpness; this is not an exact HD-rumble waveform.
#import <GameController/GameController.h>
#import <CoreHaptics/CoreHaptics.h>
#include <TargetConditionals.h>
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>
#include "controller_effects.h"

@interface DMRumbleChannel:NSObject
@property(nonatomic,strong) CHHapticEngine *engine;
@property(nonatomic,strong) id<CHHapticPatternPlayer> player;
@property(nonatomic) BOOL started;
@property(nonatomic) BOOL failed;
@property(nonatomic) dm_vibration_value applied;
@end
@implementation DMRumbleChannel @end

static dispatch_queue_t queue;
static void *queueKey=&queueKey;
static GCController *controller;
static DMRumbleChannel *channels[2];
static _Atomic unsigned capabilities;
static _Atomic int active=1;
static _Atomic unsigned generation;
static unsigned physicalCapabilities;
static unsigned failures;
static void effect_error(const char *operation,NSError *error) {
    if(failures++<32)fprintf(stderr,"[dm] [controller-effects] %s: %s\n",operation,error.localizedDescription.UTF8String?:"unavailable");
}
static void stop_channel(DMRumbleChannel *channel) {
    if(!channel)return;
    if(channel.started)[channel.player stopAtTime:CHHapticTimeImmediate error:nil];
    channel.started=NO;channel.applied=(dm_vibration_value){0};
}
static void stop_all(void) {
    for(unsigned i=0;i<2;i++)stop_channel(channels[i]);
}
static void disable_channel(unsigned side) {
    stop_channel(channels[side]);channels[side].failed=YES;
    unsigned remove=side?DM_RUMBLE_RIGHT:(physicalCapabilities&DM_RUMBLE_COMBINED)?DM_RUMBLE_COMBINED:DM_RUMBLE_LEFT;
    atomic_fetch_and(&capabilities,~remove);
}
static void refresh(void) {
    NSArray<GCController *> *attached=[GCController controllers];
    if(controller && [attached containsObject:controller] && controller.haptics)return;
    stop_all();for(unsigned i=0;i<2;i++){[channels[i].engine stopWithCompletionHandler:nil];channels[i]=nil;}
    controller=nil;physicalCapabilities=0;atomic_store(&capabilities,0);atomic_fetch_add(&generation,1);
    for(GCController *candidate in attached)if(candidate.extendedGamepad && candidate.haptics){controller=candidate;break;}
    if(!controller)return;
    NSSet<GCHapticsLocality> *localities=controller.haptics.supportedLocalities;
    unsigned bits=0;
    for(unsigned side=0;side<2;side++) {
        GCHapticsLocality locality=side?GCHapticsLocalityRightHandle:GCHapticsLocalityLeftHandle;
        if(![localities containsObject:locality])continue;
        CHHapticEngine *engine=[controller.haptics createEngineWithLocality:locality];
        if(!engine)continue;
        DMRumbleChannel *channel=[DMRumbleChannel new];channel.engine=engine;channels[side]=channel;bits|=1u<<side;
    }
    if(!bits) {
        CHHapticEngine *engine=[controller.haptics createEngineWithLocality:GCHapticsLocalityDefault];
        if(engine){channels[0]=[DMRumbleChannel new];channels[0].engine=engine;bits=DM_RUMBLE_COMBINED;}
    }
    for(unsigned side=0;side<2;side++)if(channels[side]) {
        __weak DMRumbleChannel *weak=channels[side];
        channels[side].engine.stoppedHandler=^(CHHapticEngineStoppedReason reason){
            (void)reason;dispatch_async(queue,^{DMRumbleChannel *c=weak;stop_channel(c);c.player=nil;});
        };
        channels[side].engine.resetHandler=^{dispatch_async(queue,^{DMRumbleChannel *c=weak;stop_channel(c);c.player=nil;});};
    }
    physicalCapabilities=bits;atomic_store(&capabilities,bits);
    fprintf(stderr,"[dm] [controller-effects] physical controller haptics capabilities=%u (bands approximated, motion unavailable)\n",bits);
}
static void initialized(void) {
    static dispatch_once_t once;dispatch_once(&once,^{
        dispatch_queue_attr_t attributes=dispatch_queue_attr_make_with_autorelease_frequency(DISPATCH_QUEUE_SERIAL,DISPATCH_AUTORELEASE_FREQUENCY_WORK_ITEM);
        queue=dispatch_queue_create("enginefuture.controller-effects",attributes);
        dispatch_queue_set_specific(queue,queueKey,queueKey,NULL);
        NSNotificationCenter *notifications=NSNotificationCenter.defaultCenter;
        for(NSString *name in @[GCControllerDidConnectNotification,GCControllerDidDisconnectNotification])
            [notifications addObserverForName:name object:nil queue:nil usingBlock:^(NSNotification *n){(void)n;dispatch_async(queue,^{refresh();});}];
#if TARGET_OS_IPHONE
        NSArray *off=@[@"UIApplicationWillResignActiveNotification",@"UIApplicationDidEnterBackgroundNotification"];
        NSArray *on=@[@"UIApplicationDidBecomeActiveNotification"];
#else
        NSArray *off=@[@"NSApplicationDidResignActiveNotification",@"NSWindowDidResignKeyNotification"];
        NSArray *on=@[@"NSApplicationDidBecomeActiveNotification",@"NSWindowDidBecomeKeyNotification"];
#endif
        for(NSString *name in off)[notifications addObserverForName:name object:nil queue:nil usingBlock:^(NSNotification *n){(void)n;dm_controller_effects_set_active(0);}];
        for(NSString *name in on)[notifications addObserverForName:name object:nil queue:nil usingBlock:^(NSNotification *n){(void)n;dm_controller_effects_set_active(1);}];
    });
}
static void synchronous(dispatch_block_t block) {
    initialized();if(dispatch_get_specific(queueKey))block();else dispatch_sync(queue,block);
}
static int start_channel(unsigned side) {
    DMRumbleChannel *channel=side<2?channels[side]:nil;
    if(!channel || channel.failed || !atomic_load(&active))return 0;
    if(channel.started)return 1;
    NSError *error=nil;
    if(![channel.engine startAndReturnError:&error]){effect_error("engine start",error);disable_channel(side);return 0;}
    return 1;
}
unsigned dm_controller_rumble_capabilities(void) {
    synchronous(^{refresh();});return atomic_load(&capabilities);
}
unsigned dm_controller_rumble_cached_capabilities(void) { return atomic_load(&capabilities); }
int dm_controller_rumble_permitted(void) {
    return atomic_load(&active) && dm_controller_rumble_capabilities()!=0;
}
int dm_controller_rumble_initialize(unsigned device) {
    __block int result=0;synchronous(^{refresh();if(dm_rumble_device_supported(atomic_load(&capabilities),device))result=start_channel(device);});return result;
}
int dm_controller_rumble_send(unsigned device,const dm_vibration_value *input) {
    if(!input || !dm_rumble_device_supported(atomic_load(&capabilities),device) || !atomic_load(&active))return 0;
    dm_vibration_value value;memcpy(&value,input,sizeof value);value=dm_vibration_sanitize(value);
    unsigned epoch=atomic_load(&generation);
    dispatch_async(queue,^{
        if(!atomic_load(&active) || epoch!=atomic_load(&generation))return;
        DMRumbleChannel *channel=channels[device];dm_haptic_envelope envelope=dm_vibration_envelope(value);
        if(!channel)return;
        if(envelope.intensity==0){stop_channel(channel);return;}
        dm_vibration_value previous=channel.applied;
        if(channel.started && !memcmp(&previous,&value,sizeof value))return;
        if(!start_channel(device))return;
        NSError *error=nil;
        if(!channel.player) {
            CHHapticEvent *event=[[CHHapticEvent alloc] initWithEventType:CHHapticEventTypeHapticContinuous parameters:@[
                [[CHHapticEventParameter alloc] initWithParameterID:CHHapticEventParameterIDHapticIntensity value:1],
                [[CHHapticEventParameter alloc] initWithParameterID:CHHapticEventParameterIDHapticSharpness value:0]] relativeTime:0 duration:GCHapticDurationInfinite];
            CHHapticPattern *pattern=[[CHHapticPattern alloc] initWithEvents:@[event] parameters:@[] error:&error];
            channel.player=pattern?[channel.engine createPlayerWithPattern:pattern error:&error]:nil;
        }
        if(!channel.player){effect_error("create player",error);disable_channel(device);return;}
        NSArray *parameters=@[
            [[CHHapticDynamicParameter alloc] initWithParameterID:CHHapticDynamicParameterIDHapticIntensityControl value:envelope.intensity relativeTime:0],
            [[CHHapticDynamicParameter alloc] initWithParameterID:CHHapticDynamicParameterIDHapticSharpnessControl value:envelope.sharpness relativeTime:0]];
        if(![channel.player sendParameters:parameters atTime:CHHapticTimeImmediate error:&error] ||
           (!channel.started && ![channel.player startAtTime:CHHapticTimeImmediate error:&error])) {
            effect_error("apply haptic envelope",error);disable_channel(device);return;
        }
        channel.started=YES;channel.applied=value;
    });return 1;
}
int dm_controller_rumble_applied(unsigned device,dm_vibration_value *value) {
    if(!value)return 0;memset(value,0,sizeof *value);__block int result=0;
    synchronous(^{refresh();if(device<2 && channels[device].started){*value=channels[device].applied;result=1;}});return result;
}
void dm_controller_effects_set_active(int enabled) {
    initialized();atomic_fetch_add(&generation,1);atomic_store(&active,enabled!=0);dispatch_async(queue,^{if(!enabled)stop_all();else{for(unsigned i=0;i<2;i++)channels[i].failed=NO;atomic_store(&capabilities,physicalCapabilities);refresh();}});
}
void dm_controller_effects_stop(void) {initialized();atomic_fetch_add(&generation,1);synchronous(^{stop_all();});}
