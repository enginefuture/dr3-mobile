// Exercise the production HID boundary with an explicit software output sink.
#define DM_CONTROLLER_EFFECTS_TEST 1
#include "../third_party/nxnative/dm/host/hle.h"
#undef HLE_FORCE
#define HLE_FORCE(symbol,reason,result,name,...) static result name(__VA_ARGS__)
#include "../third_party/nxnative/dm/host/hle_hid.c"
#include <assert.h>
#include <stdio.h>
#include <float.h>
static unsigned caps,sent,initialized,last_device;static int permitted=1,operation=1;
static dm_vibration_value applied;
unsigned dm_controller_rumble_capabilities(void){return caps;}
unsigned dm_controller_rumble_cached_capabilities(void){return caps;}
int dm_controller_rumble_permitted(void){return permitted && caps;}
int dm_controller_rumble_initialize(unsigned device){initialized++;last_device=device;return 1;}
int dm_controller_rumble_send(unsigned device,const dm_vibration_value *v){sent++;last_device=device;applied=dm_vibration_sanitize(*v);return 1;}
int dm_controller_rumble_applied(unsigned device,dm_vibration_value *v){(void)device;*v=applied;return 1;}
void dm_controller_effects_set_active(int active){permitted=active;}
void dm_controller_effects_stop(void){applied=(dm_vibration_value){0};}
int dm_opmode(void){return operation;}
uint64_t dm_guest_frame(void){return 0;}
uint64_t now_ns(void){return 1;}
int main(void) {
    uint32_t player=0,h[2]={0x1234,0x5678},info[2];
    assert(!h_hid_VibPermit());assert(!h_hid_VibHandles(h,2,&player,STYLE_FULLKEY));assert(h[0]==0x1234 && h[1]==0x5678);
    caps=DM_RUMBLE_LEFT|DM_RUMBLE_RIGHT;assert(h_hid_VibPermit());
    assert(h_hid_VibHandles(h,2,&player,STYLE_FULLKEY)==2 && h[0]==3 && h[1]==0x10003);
    h_hid_InitVib(&h[1]);assert(initialized==1 && last_device==1);
    h_hid_VibInfo(info,&h[0]);assert(info[0]==1 && info[1]==1);
    h_hid_VibInfo(info,&h[1]);assert(info[0]==1 && info[1]==2);
    dm_vibration_value value={0.25f,160,0.75f,320},out;
    h_hid_SendVib(&h[1],&value);assert(sent==1 && last_device==1);
    h_hid_VibActual(&out,&h[1]);assert(!memcmp(&value,&out,sizeof value));
    dm_haptic_envelope envelope=dm_vibration_envelope(value);
    assert(envelope.intensity==0.75f && fabsf(envelope.sharpness-0.561470985f)<1e-6f);
    dm_vibration_value bad={NAN,INFINITY,2,FLT_MAX};
    bad=dm_vibration_sanitize(bad);assert(bad.amp_low==0 && bad.freq_low==0 && bad.amp_high==1 && bad.freq_high==1250);
    assert(dm_vibration_envelope((dm_vibration_value){0}).intensity==0);
    uint32_t invalid=0xff000003;h_hid_SendVib(&invalid,&value);assert(sent==1);
    assert(h_hid_SendVibs(h,&value,-1)==RES_FAIL && h_hid_SendVibs(h,&value,65)==RES_FAIL);
    dm_vibration_value pair[2]={value,value};assert(h_hid_SendVibs(h,pair,2)==RES_OK && sent==3);
    caps=DM_RUMBLE_COMBINED;assert(h_hid_VibHandles(h,2,&player,STYLE_FULLKEY)==1 && h[0]==3);
    h_hid_VibInfo(info,&h[0]);assert(info[0]==1 && info[1]==0);
    h_hid_SendVib(&h[1],&value);assert(sent==3);
    caps=DM_RUMBLE_RIGHT;assert(h_hid_VibHandles(h,2,&player,STYLE_FULLKEY)==1 && h[0]==0x10003);
    operation=0;player=0x20;caps=3;
    assert(h_hid_VibHandles(h,2,&player,STYLE_HANDHELD)==2 && h[0]==0x2004 && h[1]==0x12004);
    assert(!h_hid_VibHandles(h,2,&player,STYLE_JOYDUAL));
    assert(!h_hid_SixHandles(h,2,&player,STYLE_HANDHELD));
    uint8_t motion[0x60];memset(motion,0xaa,sizeof motion);assert(!h_hid_SixStates(motion,1,h));assert(motion[0]==0xaa);
    h_hid_SixState(motion,h);for(unsigned i=0;i<sizeof motion;i++)assert(motion[i]==0);
    puts("PASS: real-capability gating, SDK 8.2 handle ABI, routing, batch output, combined/one-sided actuators, finite envelopes and honest unavailable motion");
}
