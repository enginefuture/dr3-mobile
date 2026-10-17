/* Bonjour is the public local-network discovery path on macOS and iOS.
 * NSBonjourServices must contain _dr3lan._udp. No multicast entitlement is used.
 */
#import <Foundation/Foundation.h>
#include <arpa/inet.h>
#include "lan_native.h"

@interface DR3LanDiscovery : NSObject <NSNetServiceBrowserDelegate,NSNetServiceDelegate>
@property(nonatomic,strong) NSThread *thread;
@property(nonatomic,strong) NSNetServiceBrowser *browser;
@property(nonatomic,strong) NSNetService *published;
@property(nonatomic,strong) NSMutableArray<NSNetService *> *resolving;
@end
@implementation DR3LanDiscovery
- (instancetype)init {
    if((self=[super init])) {
        _resolving=[NSMutableArray array];
        _thread=[[NSThread alloc] initWithTarget:self selector:@selector(run) object:nil];
        _thread.name=@"DR3 LAN Bonjour";
        [_thread start];
    }
    return self;
}
- (void)run {
    @autoreleasepool {
        NSRunLoop *loop=[NSRunLoop currentRunLoop];
        [loop addPort:[NSMachPort port] forMode:NSDefaultRunLoopMode];
        for(;;) { @autoreleasepool { [loop runMode:NSDefaultRunLoopMode beforeDate:[NSDate distantFuture]]; } }
    }
}
- (void)start:(NSNumber *)port {
    (void)port;
    [self stop:nil];
    self.browser=[[NSNetServiceBrowser alloc] init];
    self.browser.delegate=self;
    [self.browser searchForServicesOfType:@"_dr3lan._udp." inDomain:@"local."];
}
- (void)stop:(id)unused {
    (void)unused;
    self.browser.delegate=nil;[self.browser stop];self.browser=nil;
    self.published.delegate=nil;[self.published stop];self.published=nil;
    for(NSNetService *service in self.resolving) { service.delegate=nil;[service stop]; }
    [self.resolving removeAllObjects];
}
- (void)publish:(NSDictionary *)request {
    self.published.delegate=nil;[self.published stop];self.published=nil;
    if(![request[@"on"] boolValue])return;
    self.published=[[NSNetService alloc] initWithDomain:@"local." type:@"_dr3lan._udp." name:request[@"name"] port:[request[@"port"] intValue]];
    self.published.delegate=self;
    uint32_t ip=0,mask=0;dm_lan_ipv4(&ip,&mask);ip=htonl(ip);
    [self.published setTXTRecordData:[NSNetService dataFromTXTRecordDictionary:@{@"v":[@"1" dataUsingEncoding:NSUTF8StringEncoding],@"game":[@"01001B300B9BE000" dataUsingEncoding:NSUTF8StringEncoding],@"ip4":[NSData dataWithBytes:&ip length:4]}]];
    [self.published publish];
}
- (void)netServiceBrowserWillSearch:(NSNetServiceBrowser *)browser {
    (void)browser;dm_lan_discovery_status(1,"Bonjour browse started; local-network authorization may still be pending");
}
- (void)netServiceBrowser:(NSNetServiceBrowser *)browser didNotSearch:(NSDictionary<NSString *,NSNumber *> *)errors {
    (void)browser;dm_lan_discovery_status(-1,"Bonjour search failed or local-network permission denied");
    NSLog(@"[lan] Bonjour browse error %@",errors);
}
- (void)netServiceBrowser:(NSNetServiceBrowser *)browser didFindService:(NSNetService *)service moreComing:(BOOL)more {
    (void)browser;(void)more;
    if(self.resolving.count>=32)return;
    NSLog(@"[lan] Bonjour found %@",service.name);
    service.delegate=self;[self.resolving addObject:service];[service resolveWithTimeout:3];
}
- (void)netServiceBrowser:(NSNetServiceBrowser *)browser didRemoveService:(NSNetService *)service moreComing:(BOOL)more {
    (void)browser;(void)more;
    for(NSNetService *found in [self.resolving copy])if([found.name isEqualToString:service.name]&&[found.domain isEqualToString:service.domain]){found.delegate=nil;[found stop];[self.resolving removeObject:found];}
}
- (void)netServiceDidResolveAddress:(NSNetService *)service {
    /* Multihomed Apple hosts may resolve only another interface's address.
     * This is an untrusted local candidate, not room authorization. The C core
     * checks that it belongs to a local subnet, then authenticates JOIN. */
    NSDictionary *txt=[NSNetService dictionaryFromTXTRecordData:service.TXTRecordData];
    NSData *primary=txt[@"ip4"];
    if(primary.length==4&&service.port>0&&service.port<=65535){uint32_t ip;memcpy(&ip,primary.bytes,4);dm_lan_discovered(ip,htons((uint16_t)service.port));}
    for(NSData *data in service.addresses)if(data.length>=sizeof(struct sockaddr_in)) {
        const struct sockaddr_in *address=data.bytes;
        if(address->sin_family==AF_INET){fprintf(stderr,"[lan] Bonjour resolved ipv4=%08x port=%u\n",ntohl(address->sin_addr.s_addr),ntohs(address->sin_port));dm_lan_discovered(address->sin_addr.s_addr,address->sin_port);}
    }
}
- (void)netService:(NSNetService *)service didNotResolve:(NSDictionary<NSString *,NSNumber *> *)errors {
    (void)errors;service.delegate=nil;[service stop];[self.resolving removeObject:service];
}
- (void)netServiceDidPublish:(NSNetService *)service {
    if(service==self.published)dm_lan_discovery_status(1,"Bonjour room published");
}
- (void)netService:(NSNetService *)service didNotPublish:(NSDictionary<NSString *,NSNumber *> *)errors {
    (void)service;dm_lan_discovery_status(-1,"Bonjour room publication failed; check local-network permission");
    NSLog(@"[lan] Bonjour publish error %@",errors);
}
@end
static DR3LanDiscovery *bridge(void) { static DR3LanDiscovery *instance;static dispatch_once_t once;dispatch_once(&once,^{instance=[[DR3LanDiscovery alloc] init];});return instance; }
int dm_lan_discovery_available(void){return 1;}
void dm_lan_discovery_start(uint16_t port){DR3LanDiscovery*b=bridge();[b performSelector:@selector(start:) onThread:b.thread withObject:@(port) waitUntilDone:NO];}
void dm_lan_discovery_publish(int on,uint16_t port,const char *name){DR3LanDiscovery*b=bridge();NSDictionary*r=@{@"on":@(on),@"port":@(port),@"name":name?[NSString stringWithUTF8String:name]:@""};[b performSelector:@selector(publish:) onThread:b.thread withObject:r waitUntilDone:NO];}
void dm_lan_discovery_stop(void){DR3LanDiscovery*b=bridge();[b performSelector:@selector(stop:) onThread:b.thread withObject:nil waitUntilDone:NO];}
