// Production NVN entry -> production recording -> production Metal4 replay.
// Tests own tiny synthetic resources; no game launch or window is involved.
#define nvn_game_fps nvn_game_fps_mtl_default
#include "../third_party/nxnative/dm/gfx/nvn/nvn_mtl.m"
#undef nvn_game_fps
#include "../third_party/nxnative/dm/gfx/nvn/hle_nvn.c"
uint64_t g_t0_ns;
void *front_metal_layer(void){return NULL;}
module_t *module_of(const void *p){(void)p;return NULL;}
module_t g_mod[MAX_MOD];int g_nmod;
void svc_thread_dump(void){}
uint64_t now_ns(void){return bp_now();}
int dm_guest_as_contains(uintptr_t p){(void)p;return 0;}
static int cases,failed;
#define E(n,w,v) do{uint64_t want=(w),actual=(v);cases++;printf("%s expected=%llu actual=%llu %s\n",n,(unsigned long long)want,(unsigned long long)actual,want==actual?"OK":"FAIL");failed+=want!=actual;}while(0)
static NVNdevice dev;static NVNqueue queue;
static uint8_t command_mem[1<<20] __attribute__((aligned(16384)));
static uint8_t data_mem[65536] __attribute__((aligned(16384)));
static pool_t command_pool;
static size_t command_next;static unsigned callbacks;
static void memory_cb(NVNcommandBuffer *c,NVNcommandBufferMemoryEvent event,size_t n,void *arg){
    (void)arg;if(event!=NVN_COMMAND_BUFFER_MEMORY_EVENT_OUT_OF_COMMAND_MEMORY)abort();callbacks++;
    size_t bytes=n>256?n:256;if(command_next+bytes>sizeof command_mem)abort();
    h_nvnCommandBufferAddCommandMemory(c,(NVNmemoryPool *)&command_pool,command_next,bytes);command_next+=bytes;
}
static size_t overlap_next;
static void overlap_cb(NVNcommandBuffer *c,NVNcommandBufferMemoryEvent event,size_t n,void *arg){
    (void)arg;if(event!=NVN_COMMAND_BUFFER_MEMORY_EVENT_OUT_OF_COMMAND_MEMORY)abort();size_t bytes=n>256?n:256;
    h_nvnCommandBufferAddCommandMemory(c,(NVNmemoryPool *)&command_pool,overlap_next,bytes);overlap_next+=bytes;
}
static void init_recording(NVNcommandBuffer *c){h_nvnCommandBufferInitialize(c,&dev);h_nvnCommandBufferSetMemoryCallback(c,memory_cb);}
static void grant(NVNcommandBuffer *c,size_t offset,size_t bytes){h_nvnCommandBufferAddCommandMemory(c,(NVNmemoryPool *)&command_pool,offset,bytes);}
static uint64_t submit(NVNcommandHandle handle){h_nvnQueueSubmitCommands(&queue,1,&handle);return mtl_last_fence();}
static void wait_done(uint64_t fence){E("Metal completion",1,mtl_wait(fence,5000000000ull));E("no GPU error",0,mtl_last_commit_error());}
static p_bind_program *find_program(NVNcommandHandle handle,unsigned *calls,unsigned *jumps){
    const uint8_t *p=(const uint8_t *)(uintptr_t)handle;*calls=*jumps=0;p_bind_program *result=NULL;
    for(unsigned guard=0;guard<10000;guard++){op_hdr h;memcpy(&h,p,8);if(h.op==OP_END)return result;
        if(h.op==OP_JUMP){(*jumps)++;memcpy(&p,p+8,8);continue;}
        if(h.op==OP_CALL)(*calls)++;if(h.op==OP_BIND_PROGRAM)result=(p_bind_program *)(p+8);p+=h.size;}
    abort();
}
int main(void){@autoreleasepool{
    setenv("DM_NVN_TBDR","0",1);setenv("DM_NVN_UNIFORM_FORWARD","1",1);
    NVNdeviceBuilder db={0};h_nvnDeviceBuilderSetDefaults(&db);E("device",1,h_nvnDeviceInitialize(&dev,&db));
    NVNqueueBuilder qb={0};h_nvnQueueBuilderSetDefaults(&qb);h_nvnQueueBuilderSetDevice(&qb,&dev);E("queue",1,h_nvnQueueInitialize(&queue,&qb));
    command_pool=(pool_t){.mem=command_mem,.size=sizeof command_mem};mtl_pool_add(data_mem,sizeof data_mem);
    // Real ProgramSetShaders computes a key from registered test memory.
    uint32_t code_size=16,control_size=0x880;memcpy(data_mem+0x704,&code_size,4);memcpy(data_mem+0x20,&control_size,4);
    memset(data_mem+0x1000,0x36,16);NVNshaderData shader={(NVNbufferAddress)(data_mem+0x1000),data_mem};
    NVNprogram program;h_nvnProgramInitialize(&program,&dev);E("set shaders",1,h_nvnProgramSetShaders(&program,1,&shader));
    uint8_t old_key[8];E("key captured",1,prog_key((prog_t *)&program,0,old_key));
    // Child spans multiple grants. Parent CALLs it; Copy must flatten both.
    NVNcommandBuffer child,parent,copied,live;init_recording(&child);init_recording(&parent);init_recording(&copied);init_recording(&live);
    command_next=256;grant(&child,0,256);h_nvnCommandBufferBeginRecording(&child);h_nvnCommandBufferBindProgram(&child,&program,3);
    for(int i=0;i<12;i++){uint32_t value=11u+(uint32_t)i;h_nvnCommandBufferUpdateUniformBuffer(&child,(NVNbufferAddress)(data_mem+0x2000),256,i*4,4,&value);}
    NVNcommandHandle hc=h_nvnCommandBufferEndRecording(&child);size_t child_extent=command_next;
    grant(&parent,0x10000,256);h_nvnCommandBufferBeginRecording(&parent);h_nvnCommandBufferCallCommands(&parent,1,&hc);NVNcommandHandle hp=h_nvnCommandBufferEndRecording(&parent);
    command_next=0x20000;grant(&copied,0x20000,256);command_next+=256;h_nvnCommandBufferBeginRecording(&copied);h_nvnCommandBufferCopyCommands(&copied,1,&hp);NVNcommandHandle hcopy=h_nvnCommandBufferEndRecording(&copied);
    E("multiple command memory callbacks",1,callbacks>1);unsigned calls,jumps;p_bind_program *binding=find_program(hcopy,&calls,&jumps);
    E("copy flattened nested CALL",0,calls);E("copy contains program",1,binding!=NULL);
    E("copied inline key",0,memcmp(binding->snapshot.keys[0],old_key,8));
    // Re-record the child at the same handle address. CALL observes the current
    // source; Copy already owns its old commands, including inline program key.
    h_nvnProgramFinalize(&program);h_nvnProgramInitialize(&program,&dev);data_mem[0x1000]^=0x71;
    E("set changed shaders",1,h_nvnProgramSetShaders(&program,1,&shader));
    grant(&child,0,child_extent);h_nvnCommandBufferBeginRecording(&child);h_nvnCommandBufferBindProgram(&child,&program,3);
    uint32_t replacement=99;h_nvnCommandBufferUpdateUniformBuffer(&child,(NVNbufferAddress)(data_mem+0x2000),256,0,4,&replacement);
    NVNcommandHandle changed=h_nvnCommandBufferEndRecording(&child);E("source handle reused",hc,changed);
    grant(&live,0x30000,256);h_nvnCommandBufferBeginRecording(&live);h_nvnCommandBufferCallCommands(&live,1,&hp);NVNcommandHandle hlive=h_nvnCommandBufferEndRecording(&live);
    wait_done(submit(hlive));E("CALL observes current child",99,*(uint32_t *)(data_mem+0x2000));
    h_nvnDeviceFinalizeCommandHandle(&dev,hc);h_nvnDeviceFinalizeCommandHandle(&dev,hp);h_nvnProgramFinalize(&program);
    memset(command_mem,0xdd,child_extent);memset(command_mem+0x10000,0xdd,256);memset(data_mem,0xee,0x1010);
    wait_done(submit(hcopy));for(unsigned i=0;i<12;i++)E("COPY survives source finalize/reuse",11+i,((uint32_t *)(data_mem+0x2000))[i]);
    E("copied inline key after source destruction",0,memcmp(binding->snapshot.keys[0],old_key,8));
    uint8_t replayed_key[8];E("production replay owns copied program snapshot",1,prog_snapshot_key(S.prog,0,replayed_key));
    E("production replay uses original copied key",0,memcmp(replayed_key,old_key,8));
    NVNcommandBuffer invalid;init_recording(&invalid);grant(&invalid,0x40000,1024);h_nvnCommandBufferBeginRecording(&invalid);uint64_t before=CB(&invalid)->used;
    h_nvnCommandBufferCopyCommands(&invalid,1,&hp);E("finalized source rejected without append",before,CB(&invalid)->used);
    NVNcommandHandle bogus=1;h_nvnCommandBufferCopyCommands(&invalid,1,&bogus);E("bogus handle rejected before dereference",before,CB(&invalid)->used);
    h_nvnCommandBufferCallCommands(&invalid,1,&bogus);E("bogus CALL rejected",before,CB(&invalid)->used);
    NVNsync unfenced;h_nvnSyncInitialize(&unfenced,&dev);E("unfenced queue wait rejected",0,h_nvnQueueWaitSync(&queue,&unfenced));
    h_nvnCommandBufferWaitSync(&invalid,&unfenced);E("initialized unfenced reference is recorded",before+16,CB(&invalid)->used);
    E("unfenced CPU wait matches SDK FAILED",NVN_SYNC_WAIT_RESULT_FAILED,h_nvnSyncWait(&unfenced,0));
    NVNcommandHandle initial_wait=h_nvnCommandBufferEndRecording(&invalid);wait_done(submit(initial_wait));
    h_nvnSyncFinalize(&unfenced);E("finalized CPU wait fails",NVN_SYNC_WAIT_RESULT_FAILED,h_nvnSyncWait(&unfenced,0));
    E("double EndRecording rejected",0,h_nvnCommandBufferEndRecording(&invalid));
    // Invalid second input cannot partially append the first valid source.
    h_nvnCommandBufferBeginRecording(&invalid);before=CB(&invalid)->used;NVNcommandHandle mixed[2]={hcopy,1};
    h_nvnCommandBufferCopyCommands(&invalid,2,mixed);E("copy validates all inputs before appending",before,CB(&invalid)->used);
    (void)h_nvnCommandBufferEndRecording(&invalid);
    // A real allocator callback is deliberately allowed to overwrite source
    // command grants during the destination copy. Staging must precede it.
    NVNcommandBuffer alias;init_recording(&alias);grant(&alias,0x70000,64);overlap_next=0x20000;
    h_nvnCommandBufferSetMemoryCallback(&alias,overlap_cb);h_nvnCommandBufferBeginRecording(&alias);
    h_nvnCommandBufferCopyCommands(&alias,1,&hcopy);NVNcommandHandle halias=h_nvnCommandBufferEndRecording(&alias);
    memset(data_mem+0x2000,0,256);wait_done(submit(halias));
    for(unsigned i=0;i<12;i++)E("COPY survives allocator overwriting source grants",11+i,((uint32_t *)(data_mem+0x2000))[i]);
    // Build an actual indirect cycle through the recording APIs. Copy rejects
    // the graph atomically instead of recursing forever or partially appending.
    NVNcommandBuffer cycle_a,cycle_b;init_recording(&cycle_a);init_recording(&cycle_b);
    grant(&cycle_a,0x80000,256);h_nvnCommandBufferBeginRecording(&cycle_a);NVNcommandHandle ha=h_nvnCommandBufferEndRecording(&cycle_a);
    grant(&cycle_b,0x81000,256);h_nvnCommandBufferBeginRecording(&cycle_b);h_nvnCommandBufferCallCommands(&cycle_b,1,&ha);NVNcommandHandle hb=h_nvnCommandBufferEndRecording(&cycle_b);
    grant(&cycle_a,0x80000,256);h_nvnCommandBufferBeginRecording(&cycle_a);h_nvnCommandBufferCallCommands(&cycle_a,1,&hb);ha=h_nvnCommandBufferEndRecording(&cycle_a);
    h_nvnCommandBufferBeginRecording(&invalid);before=CB(&invalid)->used;h_nvnCommandBufferCopyCommands(&invalid,1,&ha);
    E("cyclic CALL graph rejected before append",before,CB(&invalid)->used);(void)h_nvnCommandBufferEndRecording(&invalid);
    // A controlled GPU gate proves QueueWaitSync doesn't drain/CPU-wait. Its
    // dependent recording must not complete until the gate is independently released.
    NVNcommandBuffer producer,consumer;init_recording(&producer);init_recording(&consumer);grant(&producer,0x50000,1024);grant(&consumer,0x60000,1024);
    memset(data_mem+0x4000,0x5a,256);memset(data_mem+0x5000,0,256);memset(data_mem+0x6000,0,256);
    id<MTLSharedEvent> gate=[g_dev newSharedEvent];[g_q4 waitForEvent:gate value:1];
    h_nvnCommandBufferBeginRecording(&producer);h_nvnCommandBufferCopyBufferToBuffer(&producer,(NVNbufferAddress)(data_mem+0x4000),(NVNbufferAddress)(data_mem+0x5000),256,0);NVNcommandHandle prod=h_nvnCommandBufferEndRecording(&producer);submit(prod);
    NVNsync sync;h_nvnSyncInitialize(&sync,&dev);
    h_nvnCommandBufferBeginRecording(&consumer);h_nvnCommandBufferWaitSync(&consumer,&sync);
    h_nvnQueueFenceSync(&queue,&sync,NVN_SYNC_CONDITION_ALL_GPU_COMMANDS_COMPLETE,0);
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW,300000000),dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{gate.signaledValue=1;});
    uint64_t start=now_ns();E("valid QueueWaitSync",1,h_nvnQueueWaitSync(&queue,&sync));E("QueueWaitSync does not CPU-drain",1,now_ns()-start<150000000ull);
    E("producer remains blocked by GPU gate",NVN_SYNC_WAIT_RESULT_TIMEOUT_EXPIRED,h_nvnSyncWait(&sync,0));
    h_nvnCommandBufferCopyBufferToBuffer(&consumer,(NVNbufferAddress)(data_mem+0x5000),(NVNbufferAddress)(data_mem+0x6000),256,0);NVNcommandHandle cons=h_nvnCommandBufferEndRecording(&consumer);
    uint64_t f=submit(cons);E("consumer still pending before gate",0,mtl_wait(f,0));wait_done(f);
    int equal=1;for(int i=0;i<256;i++)equal&=data_mem[0x6000+i]==0x5a;E("GPU waits preserve producer-consumer data",1,equal);
    h_nvnSyncFinalize(&sync);
    E("future fence rejected",0,mtl_queue_wait_fence(mtl_last_fence()+1));
    printf("NVN command/sync integration: %d cases, %d failed\n",cases,failed);return failed!=0;
}}
