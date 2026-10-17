// Pure motion mathematics, deliberately independent of HID publication.
// No implicit Apple-to-Nintendo basis or manufactured sensor capabilities.
#pragma once
#include <math.h>
#include <stddef.h>
#include <stdint.h>

typedef struct { double x,y,z; } dm_motion_vec;
typedef struct { double m[3][3]; } dm_motion_basis;
typedef struct { double x,y,z,w; } dm_motion_quaternion;
typedef struct {
    int64_t delta_time_ns,sampling_number;
    float acceleration_g[3],angular_velocity_turns_s[3],angle_turns[3];
    float direction[3][3];
    uint32_t attributes,reserved;
} dm_sixaxis_sdk_state;
_Static_assert(sizeof(dm_sixaxis_sdk_state)==0x60,"SDK six-axis state size");
_Static_assert(offsetof(dm_sixaxis_sdk_state,acceleration_g)==0x10,"acceleration ABI");
_Static_assert(offsetof(dm_sixaxis_sdk_state,angular_velocity_turns_s)==0x1c,"angular velocity ABI");
_Static_assert(offsetof(dm_sixaxis_sdk_state,angle_turns)==0x28,"angle ABI");
_Static_assert(offsetof(dm_sixaxis_sdk_state,direction)==0x34,"direction ABI");
_Static_assert(offsetof(dm_sixaxis_sdk_state,attributes)==0x58,"attributes ABI");

// SDK 8.2 detail::GetSixAxisSensorHandle at 0x241220. These are sensor
// device indices, not vibration-device indices (FullKey/Handheld use 2).
static inline uint32_t dm_sixaxis_handle(unsigned type,unsigned npad_id,unsigned device) {
    if(npad_id>7&&npad_id!=0x10&&npad_id!=0x20)return 0;
    if(!(((type==3||type==4)&&device==2)||(type==5&&device<2)||
        (type==6&&device==0)||(type==7&&device==1)))return 0;
    return type|(npad_id<<8)|(device<<16);
}
static inline int dm_sixaxis_valid_handle(uint32_t handle) {
    return handle&&dm_sixaxis_handle(handle&255,(handle>>8)&255,(handle>>16)&255)==handle;
}

static inline int dm_motion_finite(dm_motion_vec v) {
    return isfinite(v.x)&&isfinite(v.y)&&isfinite(v.z);
}
static inline double dm_motion_norm2(dm_motion_vec v) { return v.x*v.x+v.y*v.y+v.z*v.z; }
static inline dm_motion_vec dm_motion_cross(dm_motion_vec a,dm_motion_vec b) {
    return (dm_motion_vec){a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x};
}
static inline dm_motion_vec dm_motion_transform(dm_motion_basis b,dm_motion_vec v) {
    return (dm_motion_vec){b.m[0][0]*v.x+b.m[0][1]*v.y+b.m[0][2]*v.z,
        b.m[1][0]*v.x+b.m[1][1]*v.y+b.m[1][2]*v.z,
        b.m[2][0]*v.x+b.m[2][1]*v.y+b.m[2][2]*v.z};
}
static inline dm_motion_basis dm_motion_identity(void) {
    return (dm_motion_basis){{{1,0,0},{0,1,0},{0,0,1}}};
}
static inline double dm_motion_determinant(dm_motion_basis b) {
    return b.m[0][0]*(b.m[1][1]*b.m[2][2]-b.m[1][2]*b.m[2][1])
        -b.m[0][1]*(b.m[1][0]*b.m[2][2]-b.m[1][2]*b.m[2][0])
        +b.m[0][2]*(b.m[1][0]*b.m[2][1]-b.m[1][1]*b.m[2][0]);
}
static inline int dm_motion_proper_basis(dm_motion_basis b) {
    for(unsigned i=0;i<3;i++)for(unsigned j=0;j<3;j++) {
        double dot=0;
        for(unsigned k=0;k<3;k++) {
            if(!isfinite(b.m[i][k]))return 0;
            dot+=b.m[i][k]*b.m[j][k];
        }
        if(fabs(dot-(i==j))>1e-8)return 0;
    }
    // Reflections need different polar/axial transforms; reject them here.
    return fabs(dm_motion_determinant(b)-1)<1e-8;
}
// Explicit active, right-handed rotation on column vectors. This function does
// not assert that a particular platform's attitude uses that direction/frame.
static inline int dm_motion_quaternion_matrix(dm_motion_quaternion q,dm_motion_basis *out) {
    if(!out||!isfinite(q.x)||!isfinite(q.y)||!isfinite(q.z)||!isfinite(q.w))return 0;
    double n=hypot(hypot(q.x,q.y),hypot(q.z,q.w));
    if(!isfinite(n)||n<1e-12)return 0;
    double x=q.x/n,y=q.y/n,z=q.z/n,w=q.w/n;
    *out=(dm_motion_basis){{{1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)},
        {2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)},
        {2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)}}};
    return 1;
}
// Change both body/reference bases: R_new=P R_old P^T. No Euler decomposition.
static inline int dm_motion_change_basis(dm_motion_basis p,dm_motion_basis r,dm_motion_basis *out) {
    if(!out||!dm_motion_proper_basis(p)||!dm_motion_proper_basis(r))return 0;
    dm_motion_basis tmp={0},result={0};
    for(unsigned i=0;i<3;i++)for(unsigned j=0;j<3;j++)for(unsigned k=0;k<3;k++)tmp.m[i][j]+=p.m[i][k]*r.m[k][j];
    for(unsigned i=0;i<3;i++)for(unsigned j=0;j<3;j++)for(unsigned k=0;k<3;k++)result.m[i][j]+=tmp.m[i][k]*p.m[j][k];
    *out=result;return 1;
}
// Apple acceleration already includes gravity in g. Apple gyro is rad/s;
// the Switch input path uses turns/s. Basis must be chosen/verified by caller.
static inline int dm_motion_convert(dm_motion_basis p,dm_motion_vec acceleration_g,
        dm_motion_vec rotation_rad_s,dm_motion_vec *acceleration_out,dm_motion_vec *turns_s_out) {
    if(!acceleration_out||!turns_s_out||!dm_motion_proper_basis(p)||
       !dm_motion_finite(acceleration_g)||!dm_motion_finite(rotation_rad_s))return 0;
    dm_motion_vec a=dm_motion_transform(p,acceleration_g),g=dm_motion_transform(p,rotation_rad_s);
    double tau=6.283185307179586476925286766559;
    g=(dm_motion_vec){g.x/tau,g.y/tau,g.z/tau};
    if(!dm_motion_finite(a)||!dm_motion_finite(g))return 0;
    *acceleration_out=a;*turns_s_out=g;return 1;
}
typedef struct { dm_motion_vec angle_turns,previous_turns_s; int have_previous; } dm_motion_integrator;
// Angle is integrated sensor-local angular velocity, not an Euler attitude.
// The caller resets on start/disconnect/time discontinuity. Rejected samples
// change neither previous sample nor accumulated state.
static inline int dm_motion_integrate(dm_motion_integrator *s,dm_motion_vec turns_s,double dt_s) {
    if(!s||!dm_motion_finite(turns_s)||!isfinite(dt_s)||dt_s<=0||dt_s>0.1)return 0;
    dm_motion_vec previous=s->have_previous?s->previous_turns_s:turns_s;
    dm_motion_vec a={s->angle_turns.x+(previous.x+turns_s.x)*0.5*dt_s,
        s->angle_turns.y+(previous.y+turns_s.y)*0.5*dt_s,
        s->angle_turns.z+(previous.z+turns_s.z)*0.5*dt_s};
    if(!dm_motion_finite(a))return 0;
    s->angle_turns=a;s->previous_turns_s=turns_s;s->have_previous=1;return 1;
}
// D3's bounded static consumer only needs these two scalar metrics. If a real
// stationary reference g0 is established and normalized, |a-g0|^2 is invariant under any
// orthogonal basis mapping g0 to Nintendo's (0,0,-1). Thus yaw/attitude are not
// needed for D3 shake detection. This is not a full SixAxisSensorState encoder.
static inline int dm_motion_d3_metrics(dm_motion_vec a_g,dm_motion_vec g0_g,
        dm_motion_vec omega_rad_s,double *accel_deviation2,double *gyro_turns2) {
    if(!accel_deviation2||!gyro_turns2||!dm_motion_finite(a_g)||
       !dm_motion_finite(g0_g)||!dm_motion_finite(omega_rad_s))return 0;
    double n=dm_motion_norm2(g0_g);
    if(n<0.81||n>1.21)return 0; // caller must additionally establish stationarity
    double inv=1/sqrt(n);g0_g=(dm_motion_vec){g0_g.x*inv,g0_g.y*inv,g0_g.z*inv};
    double tau=6.283185307179586476925286766559;
    dm_motion_vec d={a_g.x-g0_g.x,a_g.y-g0_g.y,a_g.z-g0_g.z};
    double a2=dm_motion_norm2(d),g2=dm_motion_norm2(omega_rad_s)/(tau*tau);
    if(!isfinite(a2)||!isfinite(g2))return 0;
    *accel_deviation2=a2;*gyro_turns2=g2;return 1;
}
