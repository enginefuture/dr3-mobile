// Shared readiness checks for private, completely transferred resource files.
#pragma once
#import <Foundation/Foundation.h>
#include <stdio.h>

static int assets_ready(NSString *directory, NSDictionary *inventory, NSString *kind) {
    NSFileManager *fm = NSFileManager.defaultManager;
    if (![inventory isKindOfClass:NSDictionary.class] || !inventory.count || !directory) {
        fprintf(stderr,"boot: missing %s resource inventory/location\n",kind.UTF8String); return 0;
    }
    NSString *root = directory.stringByResolvingSymlinksInPath;
    for (NSString *relative in inventory) {
        if (![relative isKindOfClass:NSString.class] || relative.isAbsolutePath || [relative.pathComponents containsObject:@".."] || ![inventory[relative] isKindOfClass:NSNumber.class]) return 0;
        NSString *path = [directory stringByAppendingPathComponent:relative].stringByResolvingSymlinksInPath;
        if (![path hasPrefix:[root stringByAppendingString:@"/"]]) return 0;
        NSDictionary *attributes = [fm attributesOfItemAtPath:path error:nil];
        if (![attributes[NSFileType] isEqual:NSFileTypeRegular] || [attributes[NSFileSize] unsignedLongLongValue] != [inventory[relative] unsignedLongLongValue]) {
            fprintf(stderr,"boot: incomplete %s asset %s\n",kind.UTF8String,relative.UTF8String); return 0;
        }
    }
    return 1;
}

