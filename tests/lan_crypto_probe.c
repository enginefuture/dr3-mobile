/* Exercise the actual forced implementation, not a duplicate random wrapper.
 * Room/network entrypoints are linked but never invoked by this probe. */
#include "hle_lan_hooks.c"
#include <assert.h>
module_t g_mod[MAX_MOD];
int g_nmod;
void hle_signal_system_event(void *event){(void)event;abort();}
void hle_bind_system_event(void *event,int autoclear){(void)event;(void)autoclear;abort();}
void dm_bigstack_enter(void){abort();} /* The probe calls the implementation directly. */
int main(void){
    assert(!strcmp(hle_force_lan_crypto_random.name,"_ZN2nn6crypto36GenerateCryptographicallyRandomBytesEPvm"));
    assert(hle_force_lan_crypto_random.fn==(const void*)lan_crypto_random_bs);
    lan_crypto_random(NULL,0);
    size_t sizes[]={1,17,128,4096};
    for(unsigned j=0;j<sizeof(sizes)/sizeof(*sizes);j++){
        unsigned char a[4128],b[4128];memset(a,0xa5,sizeof(a));memset(b,0x5a,sizeof(b));
        size_t n=sizes[j];lan_crypto_random(a+16,n);lan_crypto_random(b+16,n);
        for(int i=0;i<16;i++){assert(a[i]==0xa5&&b[i]==0x5a);assert(a[16+n+i]==0xa5&&b[16+n+i]==0x5a);}
        if(n>=17)assert(memcmp(a+16,b+16,n));
    }
    puts("actual CSPRNG hook bounds and registration passed");return 0;
}
