// A queued bind and active queue state must survive reuse/unmapping of both
// the guest NVNprogram and the recorded command memory.
#include "../third_party/nxnative/dm/gfx/nvn/nvn_obj.h"
#include <assert.h>
#include <sys/mman.h>
#include <unistd.h>
#include <stdio.h>
static unsigned reads;
static int keys(const prog_t *p,unsigned stage,uint8_t out[8]) {
    assert(p->magic==MAGIC('P','R','O','G'));reads++;
    for(unsigned i=0;i<8;i++)out[i]=(uint8_t)(stage*16+i+3);
    return 1;
}
static int missing_key(const prog_t *p,unsigned stage,uint8_t out[8]) {
    (void)p;(void)stage;(void)out;return 0;
}
int main(void) {
    size_t size=(size_t)sysconf(_SC_PAGESIZE);
    prog_t *original=mmap(NULL,size,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANON,-1,0);
    p_bind_program *command=mmap(NULL,size,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANON,-1,0);
    assert(original!=MAP_FAILED && command!=MAP_FAILED);
    original->magic=MAGIC('P','R','O','G');original->nstage=6;original->serial=42;
    for(unsigned i=0;i<6;i++){original->sd[i].data=0x111000+i;original->sd[i].control=(void *)(uintptr_t)(0xdead000+i);}
    command->stages=3;command->has_program=1;
    assert(prog_snapshot_capture(&command->snapshot,original,keys));assert(reads==6);
    assert(sizeof(prog_t)<=sizeof(NVNprogram));
    memset(original,0xa9,sizeof *original);assert(mprotect(original,size,PROT_NONE)==0);
    p_bind_program copied=*command; // The internal record must remain valid when its bytes are relocated.
    assert(mprotect(command,size,PROT_NONE)==0);
    const prog_t *queued=recorded_program(&copied);assert(queued && queued->serial==42);
    for(unsigned st=0;st<6;st++) {
        uint8_t key[8];assert(prog_snapshot_key(queued,st,key));
        for(unsigned i=0;i<8;i++)assert(key[i]==st*16+i+3);
    }
    prog_snapshot_t active;const prog_t *bound=prog_snapshot_bind(&active,queued);
    memset(&copied,0x7b,sizeof copied); // The queue state must not alias recording memory.
    uint8_t key[8];assert(bound->serial==42 && prog_snapshot_key(bound,5,key) && key[0]==83);
    assert(reads==6);assert(!prog_snapshot_key(bound,6,key));
    assert(!prog_snapshot_capture(&active,bound,keys)); // Do not silently treat a captured record as a live guest object.
    prog_t bad={0};bad.magic=MAGIC('P','R','O','G');bad.nstage=7;
    assert(!prog_snapshot_capture(&active,&bad,keys));assert(reads==6);
    bad.nstage=1;assert(!prog_snapshot_capture(&active,&bad,missing_key));
    assert(active.program.serial==42); // Failure never publishes a half snapshot.
    assert(!prog_snapshot_bind(&active,NULL));
    copied=(p_bind_program){0};assert(!recorded_program(&copied));
    assert(munmap(original,size)==0 && munmap(command,size)==0);
    puts("PASS: immutable program keys, reused guest storage, relocated command memory, active-state ownership and invalid inputs");
    return 0;
}
