#include "../native/sixaxis_math.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static int near(double a,double b){return fabs(a-b)<1e-9;}
static void vector(dm_motion_vec a,dm_motion_vec b){assert(near(a.x,b.x)&&near(a.y,b.y)&&near(a.z,b.z));}
int main(void) {
    const double pi=3.14159265358979323846,s=sqrt(0.5);
    assert(dm_sixaxis_handle(3,0,2)==0x20003);
    assert(dm_sixaxis_handle(4,0x20,2)==0x22004);
    assert(dm_sixaxis_handle(5,7,0)==0x705&&dm_sixaxis_handle(5,7,1)==0x10705);
    assert(dm_sixaxis_handle(6,0,0)==6&&dm_sixaxis_handle(7,0,1)==0x10007);
    assert(dm_sixaxis_handle(3,0x10,2)==0x21003);
    assert(!dm_sixaxis_handle(3,0,0)&&!dm_sixaxis_handle(4,8,2));
    assert(!dm_sixaxis_handle(7,0,0)&&!dm_sixaxis_handle(6,0,1));
    assert(dm_sixaxis_valid_handle(0x22004)&&!dm_sixaxis_valid_handle(0x1022004));
    dm_motion_basis z90,x90;
    assert(dm_motion_quaternion_matrix((dm_motion_quaternion){0,0,s,s},&z90));
    assert(dm_motion_quaternion_matrix((dm_motion_quaternion){s,0,0,s},&x90));
    assert(dm_motion_proper_basis(z90)&&dm_motion_proper_basis(x90));
    vector(dm_motion_transform(z90,(dm_motion_vec){1,0,0}),(dm_motion_vec){0,1,0});
    vector(dm_motion_transform(x90,(dm_motion_vec){0,1,0}),(dm_motion_vec){0,0,1});
    dm_motion_vec a={1.2,-0.4,3},b={-2,1,0.5};
    vector(dm_motion_cross(dm_motion_transform(z90,a),dm_motion_transform(z90,b)),dm_motion_transform(z90,dm_motion_cross(a,b)));
    assert(near(dm_motion_norm2(a),dm_motion_norm2(dm_motion_transform(z90,a))));
    dm_motion_basis changed;
    assert(dm_motion_change_basis(x90,z90,&changed));
    vector(dm_motion_transform(changed,dm_motion_transform(x90,a)),dm_motion_transform(x90,dm_motion_transform(z90,a)));
    dm_motion_basis scaled;
    assert(dm_motion_quaternion_matrix((dm_motion_quaternion){0,0,7*s,7*s},&scaled));
    vector(dm_motion_transform(scaled,a),dm_motion_transform(z90,a));
    assert(!dm_motion_quaternion_matrix((dm_motion_quaternion){0},&scaled));
    assert(!dm_motion_quaternion_matrix((dm_motion_quaternion){NAN,0,0,1},&scaled));
    dm_motion_basis reflection=dm_motion_identity();reflection.m[2][2]=-1;
    assert(!dm_motion_proper_basis(reflection));
    dm_motion_vec ag={8,8,8},turns={9,9,9};
    assert(dm_motion_convert(dm_motion_identity(),(dm_motion_vec){0,0,-1},(dm_motion_vec){pi,0,-2*pi},&ag,&turns));
    vector(ag,(dm_motion_vec){0,0,-1});vector(turns,(dm_motion_vec){0.5,0,-1});
    assert(!dm_motion_convert(reflection,a,b,&ag,&turns));
    assert(!dm_motion_convert(z90,(dm_motion_vec){INFINITY,0,0},b,&ag,&turns));
    vector(turns,(dm_motion_vec){0.5,0,-1});
    dm_motion_integrator integral={0};
    for(int i=0;i<100;i++)assert(dm_motion_integrate(&integral,(dm_motion_vec){0,0,0.5},0.01));
    vector(integral.angle_turns,(dm_motion_vec){0,0,0.5});
    // A direction's Euler angle wraps; cumulative turns do not.
    for(int i=0;i<400;i++)assert(dm_motion_integrate(&integral,(dm_motion_vec){0,0,0.5},0.01));
    vector(integral.angle_turns,(dm_motion_vec){0,0,2.5});
    dm_motion_integrator saved=integral;
    assert(!dm_motion_integrate(&integral,b,0));assert(!dm_motion_integrate(&integral,b,0.11));
    assert(!dm_motion_integrate(&integral,(dm_motion_vec){NAN,0,0},0.01));
    assert(!memcmp(&integral,&saved,sizeof saved));
    double ad,gd,ar,gr;
    dm_motion_vec rest={0,-1,0},sample={0.2,-0.7,0.4},omega={pi,0,0};
    assert(dm_motion_d3_metrics(sample,rest,omega,&ad,&gd));
    assert(near(ad,0.29)&&near(gd,0.25));
    // Explicitly align measured rest with Nintendo's down vector, then check
    // the exact scalar expression observed in all five D3 polling paths.
    vector(dm_motion_transform(x90,rest),(dm_motion_vec){0,0,-1});
    assert(dm_motion_convert(x90,sample,omega,&ag,&turns));
    assert(near(ad,ag.x*ag.x+ag.y*ag.y+(ag.z+1)*(ag.z+1)));
    assert(near(gd,dm_motion_norm2(turns)));
    assert(dm_motion_d3_metrics(dm_motion_transform(z90,sample),dm_motion_transform(z90,rest),dm_motion_transform(z90,omega),&ar,&gr));
    assert(near(ad,ar)&&near(gd,gr));
    assert(!dm_motion_d3_metrics(sample,(dm_motion_vec){0},omega,&ar,&gr));
    puts("PASS: SDK 0x60 offsets/handles, rad/s to turns/s, cumulative turns, proper rotations, basis covariance, D3 invariant metrics, invalid data rejected");
    return 0;
}
