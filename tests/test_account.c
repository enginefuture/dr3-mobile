#include "../third_party/nxnative/dm/host/hle.h"
#undef HLE_FORCE
#define HLE_FORCE(symbol, reason, result, name, ...) static result name(__VA_ARGS__)
#include "../third_party/nxnative/dm/host/hle_account.c"
#include <assert.h>

int main(void) {
    struct { uint64_t before; UserHandle handle; uint64_t after; } box;
    memset(&box, 0xa5, sizeof box);
    uint64_t guard = box.before;
    assert(h_acc_OpenPre(NULL) != RES_OK);
    assert(h_acc_OpenPre(&box.handle) == RES_OK);
    assert(box.before == guard && box.after == guard);
    Uid uid = {{0, 0}};
    assert(h_acc_GetUserId(&uid, &box.handle) == RES_OK);
    assert(uid.v[0] == k_uid.v[0] && uid.v[1] == k_uid.v[1]);
    uint8_t exists = 0;
    assert(h_acc_Exists(&exists, &uid) == RES_OK && exists);
    return 0;
}
