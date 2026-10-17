// Passive capability query only. Never starts an engine or sends vibration.
#import <GameController/GameController.h>
#import <CoreHaptics/CoreHaptics.h>
#include "../native/controller_effects.h"
#include <assert.h>
#include <stdio.h>
int main(void) { @autoreleasepool {
    GCController *snapshot=[GCController controllerWithExtendedGamepad];
    printf("Snapshot haptics advertised by Apple: %s\n",snapshot.haptics?"yes":"no");
    [[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:1.0]];
    NSArray *attached=GCController.controllers;unsigned real=0,motion=0;
    for(GCController *controller in attached) {
        if(controller.extendedGamepad && controller.haptics)real++;
        if(controller.motion.hasAttitude && controller.motion.hasRotationRate)motion++;
    }
    unsigned caps=dm_controller_rumble_capabilities();
    assert(!(caps&~7u));if(!real)assert(!caps);
    dm_vibration_value applied;assert(!dm_controller_rumble_applied(0,&applied));
    assert(applied.amp_low==0 && applied.amp_high==0);
    NSError *error=nil;
    CHHapticEvent *event=[[CHHapticEvent alloc] initWithEventType:CHHapticEventTypeHapticContinuous parameters:@[] relativeTime:0 duration:GCHapticDurationInfinite];
    CHHapticPattern *pattern=[[CHHapticPattern alloc] initWithEvents:@[event] parameters:@[] error:&error];
    if(!pattern)fprintf(stderr,"pattern: %s\n",error.localizedDescription.UTF8String);assert(pattern);
    printf("PASS: passive probe: physical=%lu haptics_capable=%u motion_capable=%u capabilities=%u; no engine start/output, hardware actuation untested\n",(unsigned long)attached.count,real,motion,caps);
}return 0;}
