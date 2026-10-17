#import <Foundation/Foundation.h>
#include "../native/asset_inventory.h"
#include <assert.h>
int main(void) { @autoreleasepool {
    NSFileManager *fm=NSFileManager.defaultManager;
    NSString *root=[NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
    assert([fm createDirectoryAtPath:[root stringByAppendingPathComponent:@"11"] withIntermediateDirectories:YES attributes:nil error:nil]);
    NSString *file=[root stringByAppendingPathComponent:@"11/sample.cpk"];
    assert([[@"payload" dataUsingEncoding:NSUTF8StringEncoding] writeToFile:file atomically:YES]);
    NSDictionary *expected=@{@"11/sample.cpk":@7};
    assert(assets_ready(root,expected,@"test"));
    assert(!assets_ready(root,@{@"11/sample.cpk":@8},@"truncated"));
    assert(!assets_ready(root,@{@"11/absent.cpk":@0},@"absent"));
    assert(!assets_ready(root,@{@"11":@0},@"directory"));
    assert(!assets_ready(root,@{@"../outside":@7},@"parent"));
    assert(!assets_ready(root,@{@"/absolute":@7},@"absolute"));
    assert(!assets_ready(root,@{@"11/sample.cpk":@"7"},@"untyped"));
    assert(!assets_ready(root,@{},@"empty"));
    NSString *outside=[NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
    assert([[@"payload" dataUsingEncoding:NSUTF8StringEncoding] writeToFile:outside atomically:YES]);
    assert([fm createSymbolicLinkAtPath:[root stringByAppendingPathComponent:@"link"] withDestinationPath:outside error:nil]);
    assert(!assets_ready(root,@{@"link":@7},@"escaped symlink"));
    assert([fm removeItemAtPath:outside error:nil]);
    assert([fm removeItemAtPath:root error:nil]);
    puts("PASS: complete private resources, partial/absent files, path confinement and typed manifests");
} return 0; }
