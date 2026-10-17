#import <Foundation/Foundation.h>
#include "../third_party/nxnative/dm/gfx/nvn/nvn_vertex_fetch.h"
#include <stdio.h>
int main(int argc,const char **argv) { @autoreleasepool {
    if(argc!=3)return 2;
    NSString *source=[NSString stringWithContentsOfFile:@(argv[1]) encoding:NSUTF8StringEncoding error:nil];
    NSString *why=nil,*result=source?nvn_vertex_fetch_adapt(source,strtoull(argv[2],NULL,16),&why):nil;
    if(!result){fprintf(stderr,"%s\n",why.UTF8String?:"missing source");return 1;}
    NSData *data=[result dataUsingEncoding:NSUTF8StringEncoding];fwrite(data.bytes,1,data.length,stdout);return 0;
}}
