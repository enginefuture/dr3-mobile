// Shared Mac/iOS physical-controller effect ABI. No virtual actuators or motion.
#pragma once
#include <stdint.h>
#include <math.h>

typedef struct { float amp_low,freq_low,amp_high,freq_high; } dm_vibration_value;
typedef struct { float intensity,sharpness; } dm_haptic_envelope;
enum { DM_RUMBLE_LEFT=1,DM_RUMBLE_RIGHT=2,DM_RUMBLE_COMBINED=4 };
_Static_assert(sizeof(dm_vibration_value)==16,"Nintendo vibration value ABI");

static inline float dm_effect_unit(float value) {
    return !isfinite(value) || value<=0?0:value>1?1:value;
}
static inline dm_vibration_value dm_vibration_sanitize(dm_vibration_value v) {
    v.amp_low=dm_effect_unit(v.amp_low);v.amp_high=dm_effect_unit(v.amp_high);
    if(!isfinite(v.freq_low) || v.freq_low<=0){v.freq_low=0;v.amp_low=0;}
    if(!isfinite(v.freq_high) || v.freq_high<=0){v.freq_high=0;v.amp_high=0;}
    if(v.freq_low>1250)v.freq_low=1250;if(v.freq_high>1250)v.freq_high=1250;
    return v;
}
static inline dm_haptic_envelope dm_vibration_envelope(dm_vibration_value input) {
    dm_vibration_value v=dm_vibration_sanitize(input);float total=v.amp_low+v.amp_high;
    float frequency=total>0?(v.freq_low*v.amp_low+v.freq_high*v.amp_high)/total:40;
    float sharpness=frequency>0?log2f(frequency/40.0f)/5.0f:0;
    return (dm_haptic_envelope){fmaxf(v.amp_low,v.amp_high),dm_effect_unit(sharpness)};
}
static inline int dm_rumble_device_supported(unsigned capabilities,unsigned device) {
    return device<2 && ((capabilities&(1u<<device)) || (device==0 && (capabilities&DM_RUMBLE_COMBINED)));
}
static inline uint32_t dm_rumble_handle(unsigned style,uint32_t player,unsigned device) {
    // Verified in D3 SDK 8.2 detail::GetVibrationDeviceHandles: full=3, handheld=4.
    unsigned index=style==1?3:style==2?4:0;
    return index && player<=0x20 && device<2 ? index|(player<<8)|(device<<16):0;
}
static inline int dm_rumble_decode(uint32_t handle,uint32_t player) {
    unsigned style=handle&255,device=(handle>>16)&255;
    return !(handle>>24) && (style==3 || style==4) && ((handle>>8)&255)==player && device<2 ? (int)device:-1;
}

#if defined(DM_CONTROLLER_EFFECTS_OPTIONAL) && !defined(DM_CONTROLLER_EFFECTS_TEST)
#define DM_EFFECT_API __attribute__((weak_import))
#else
#define DM_EFFECT_API
#endif
#ifdef __cplusplus
extern "C" {
#endif
unsigned dm_controller_rumble_capabilities(void) DM_EFFECT_API;
unsigned dm_controller_rumble_cached_capabilities(void) DM_EFFECT_API;
int dm_controller_rumble_permitted(void) DM_EFFECT_API;
int dm_controller_rumble_initialize(unsigned device) DM_EFFECT_API;
int dm_controller_rumble_send(unsigned device,const dm_vibration_value *value) DM_EFFECT_API;
int dm_controller_rumble_applied(unsigned device,dm_vibration_value *value) DM_EFFECT_API;
void dm_controller_effects_set_active(int active) DM_EFFECT_API;
void dm_controller_effects_stop(void) DM_EFFECT_API;
#ifdef __cplusplus
}
#endif
#undef DM_EFFECT_API
