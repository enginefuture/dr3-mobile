#include "lan_native.h"
#include <arpa/inet.h>
#include <assert.h>
#include <errno.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
static uint64_t monotonic_ms(void){struct timespec t;assert(!clock_gettime(CLOCK_MONOTONIC,&t));return (uint64_t)t.tv_sec*1000+t.tv_nsec/1000000;}
static uint16_t scene(void){const char*value=getenv("DM_LAN_TEST_SCENE");if(!value)return 7;char*end;long n=strtol(value,&end,10);assert(!*end&&n>1&&n<65535);return (uint16_t)n;}
static void address(uint8_t out[16],const char*ip,uint16_t port){memset(out,0,16);out[0]=16;out[1]=2;uint16_t p=htons(port);memcpy(out+2,&p,2);assert(inet_pton(AF_INET,ip,out+4)==1);}
static int bound(int type,uint16_t*port){int fd=dm_lan_socket(2,type,0);assert(fd>=0);uint8_t a[16];address(a,getenv("DM_LAN_BIND_IP"),0);assert(!dm_lan_socket_bind(fd,a,16));unsigned n=16;assert(!dm_lan_socket_name(fd,a,&n,0));memcpy(port,a+2,2);*port=ntohs(*port);return fd;}
static dm_lan_security security(void){dm_lan_security s={.mode=2,.passphrase_size=32};memset(s.passphrase,11,32);return s;}
static int host(int destroy_joined){
    assert(!dm_lan_initialize());assert(dm_lan_state()==1);uint16_t udpport,tcpport;int udp=bound(2,&udpport),tcp=bound(1,&tcpport);assert(!dm_lan_socket_listen(tcp,4));assert(!dm_lan_socket_fcntl(udp,4,0x800));assert(!dm_lan_socket_fcntl(tcp,4,0x800));
    assert(!dm_lan_open(1));uint16_t advert[2]={htons(udpport),htons(tcpport)};assert(!dm_lan_advertise(advert,sizeof(advert)));dm_lan_network_config cfg={.intent={.communication_id=0x01001B300B9BE000LL,.scene_id=scene()},.max_nodes=2,.version=123};dm_lan_security s=security();dm_lan_user user={.name="synthetic-host"};assert(!dm_lan_create(&cfg,&s,&user));
    printf("{\"control_port\":%u}\n",dm_lan_control_port());fflush(stdout);int udpdone=0,tcpdone=0,departed=0,connected=0;
    for(int tick=0;tick<500;tick++){
        struct pollfd p[2]={{.fd=udp,.events=POLLIN},{.fd=tcp,.events=POLLIN}};assert(dm_lan_socket_poll(p,2,50)>=0);
        if(p[0].revents&POLLIN){char b[16];uint8_t a[16];unsigned n=16;assert(dm_lan_socket_recvfrom(udp,b,sizeof(b),0,a,&n)==4);assert(!memcmp(b,"ping",4));assert(dm_lan_socket_sendto(udp,"pong",4,0,a,n)==4);udpdone++;}
        if(p[1].revents&POLLIN){uint8_t a[16];unsigned n=16;int fd=dm_lan_socket_accept(tcp,a,&n);assert(fd>=0);assert(!dm_lan_socket_fcntl(fd,4,0));char b[16];assert(dm_lan_socket_recv(fd,b,5,0x40)==5);assert(!memcmp(b,"hello",5));assert(dm_lan_socket_send(fd,"world",5,0)==5);assert(!dm_lan_socket_shutdown(fd,1));assert(!dm_lan_socket_close(fd));tcpdone++;}
        dm_lan_network_info info;dm_lan_node_update updates[8];assert(!dm_lan_info(&info,updates,8));if(info.node_count>=2)connected=1;if(destroy_joined&&connected){usleep(250000);assert(!dm_lan_disconnect(1));printf("{\"destroyed\":true}\n");fflush(stdout);usleep(150000);dm_lan_finalize();return 0;}for(int i=1;i<8;i++)if(updates[i].changed&2)departed=1;
        if(udpdone&&tcpdone&&connected&&departed&&info.node_count==1){printf("{\"udp\":%d,\"tcp\":%d,\"departed\":%d,\"nodes\":%d}\n",udpdone,tcpdone,departed,info.node_count);fflush(stdout);assert(!dm_lan_disconnect(1));assert(dm_lan_state()==2);dm_lan_finalize();return 0;}
    }fprintf(stderr,"probe timeout udp=%d tcp=%d connected=%d departed=%d\n",udpdone,tcpdone,connected,departed);dm_lan_finalize();return 2;
}
static int client(int await_destroy,int transition){
    assert(!dm_lan_initialize());int retained_udp=-1;uint16_t retained_port=0;
    if(transition){
        /* Match the real game: a BSD UDP socket already exists while its LDN
         * room is destroyed. The guest still owns that descriptor, then closes
         * it itself only AFTER Connect succeeds, before recreating the socket. */
        retained_udp=bound(2,&retained_port);assert(!dm_lan_open(1));
        dm_lan_network_config old={.intent={.communication_id=0x01001B300B9BE000LL,.scene_id=99},.max_nodes=2,.version=123};
        dm_lan_security own_security=security();dm_lan_user own_user={.name="previous-own-room"};
        assert(!dm_lan_create(&old,&own_security,&own_user));assert(!dm_lan_disconnect(1));assert(dm_lan_state()==2);assert(!dm_lan_close(1));
    }
    assert(!dm_lan_open(0));dm_lan_network_info rooms[4];int count=0;dm_lan_scan_filter filter={.id.intent={.communication_id=0x01001B300B9BE000LL,.scene_id=scene()},.type=2,.flags=0x25};
    /* Other real Bonjour rooms can wake Scan early. Bound discovery by elapsed
     * time, not a fixed number of condition-variable wakeups. */
    uint64_t until=monotonic_ms()+8000;
    do{assert(!dm_lan_scan(rooms,&count,4,&filter,0));if(count)break;usleep(50000);}while(monotonic_ms()<until);
    if(count!=1)fprintf(stderr,"DISCOVERY_DEADLINE scene=%u rooms=%d\n",scene(),count);
    assert(count==1);filter.id.intent.scene_id=0xffff;assert(!dm_lan_scan(rooms+1,&count,3,&filter,0));assert(count==0);filter.id.intent.scene_id=scene();assert(!dm_lan_scan(rooms,&count,4,&filter,0));assert(count==1);
    dm_lan_security s=security(),bad=s;bad.passphrase[0]^=1;dm_lan_user u={.name="synthetic-client"};assert(dm_lan_connect(rooms,&bad,&u,123,0)==-1);assert(dm_lan_state()==4);assert(dm_lan_connect(rooms,&s,&u,124,0)==-1);assert(dm_lan_state()==4);assert(!dm_lan_connect(rooms,&s,&u,123,0));assert(dm_lan_state()==5);
    if(transition){
        /* Original main c13298 calls bdSocket::Close before create/bind. Closing
         * the cached guest descriptor must succeed even after LDN teardown. */
        int close_result=dm_lan_socket_close(retained_udp);
        if(close_result)fprintf(stderr,"LDN_TRANSITION_CLOSE fd=%d result=%d guest_errno=%d\n",retained_udp,close_result,dm_lan_socket_errno());
        assert(close_result==0);
    }
    struct {dm_lan_network_info info;unsigned char guard[16];} snapshot;memset(&snapshot,0xa5,sizeof(snapshot));dm_lan_node_update updates[8];assert(dm_lan_info(&snapshot.info,updates,7)==-1);assert(!dm_lan_info(&snapshot.info,updates,8));assert(snapshot.info.node_count==2);assert(snapshot.info.security_mode==2);for(int i=0;i<16;i++)assert(snapshot.guard[i]==0xa5);assert(updates[0].changed&1);assert(updates[1].changed&1);assert(!dm_lan_info(&snapshot.info,updates,8));for(int i=0;i<8;i++)assert(updates[i].changed==0);
    if(await_destroy){for(int i=0;i<60&&dm_lan_state()==5;i++)usleep(50000);assert(dm_lan_state()==4);assert(dm_lan_disconnect_reason()==3);dm_lan_finalize();printf("{\"destroy_client\":\"passed\"}\n");return 0;}
    uint16_t ports[2];memcpy(ports,snapshot.info.advertise,4);uint8_t hostip[16];char ip[16];uint32_t net=htonl(snapshot.info.nodes[0].ipv4);assert(inet_ntop(AF_INET,&net,ip,sizeof(ip)));address(hostip,ip,ntohs(ports[0]));uint16_t local;int udp;
    if(transition){
        udp=dm_lan_socket(2,2,0);assert(udp>=0);assert(dm_lan_socket_fcntl(udp,3,0)>=0);assert(!dm_lan_socket_fcntl(udp,4,0x800));
        int broadcast=1;unsigned length=sizeof(broadcast);assert(!dm_lan_socket_option(udp,0xffff,0x20,&broadcast,&length,1));
        uint8_t own_address[16];address(own_address,getenv("DM_LAN_BIND_IP"),retained_port);assert(!dm_lan_socket_bind(udp,own_address,16));
        length=16;assert(!dm_lan_socket_name(udp,own_address,&length,0));uint16_t actual;memcpy(&actual,own_address+2,2);assert(ntohs(actual)==retained_port);
        puts("LDN_TRANSITION_CLOSE_CREATE_FCNTL_BROADCAST_BIND passed");fflush(stdout);
    }else udp=bound(2,&local);
    assert(!dm_lan_socket_fcntl(udp,4,0x800));assert(dm_lan_socket_fcntl(udp,3,0)&0x800);char b[16];assert(dm_lan_socket_recv(udp,b,1,0)==-1&&dm_lan_socket_errno()==11);assert(dm_lan_socket_sendto(udp,"ping",4,0,hostip,16)==4);
    uint32_t readset[32]={0};readset[udp/32]|=1u<<(udp%32);int64_t timeout[2]={2,0};assert(dm_lan_socket_select(udp+1,readset,NULL,NULL,timeout)==1);assert(readset[udp/32]&(1u<<(udp%32)));uint8_t peer[16];unsigned n=16;assert(dm_lan_socket_recvfrom(udp,b,sizeof(b),2,peer,&n)==4);assert(!memcmp(b,"pong",4));assert(dm_lan_socket_recvfrom(udp,b,sizeof(b),0,peer,&n)==4);assert(!memcmp(peer+4,hostip+4,4));address(hostip,"8.8.8.8",53);assert(dm_lan_socket_sendto(udp,"blocked",7,0,hostip,16)==-1&&dm_lan_socket_errno()==13);assert(!dm_lan_socket_close(udp));assert(dm_lan_socket_close(udp)==-1&&dm_lan_socket_errno()==9);
    struct pollfd invalid={.fd=1000,.events=POLLIN};assert(dm_lan_socket_poll(&invalid,1,20)==1&&(invalid.revents&POLLNVAL));int tcp=dm_lan_socket(2,1,0);assert(tcp>=0);address(hostip,ip,ntohs(ports[1]));assert(!dm_lan_socket_fcntl(tcp,4,0x800));int connecting=dm_lan_socket_connect(tcp,hostip,16);assert(connecting==0||(connecting==-1&&dm_lan_socket_errno()==115));struct pollfd writable={.fd=tcp,.events=POLLOUT};assert(dm_lan_socket_poll(&writable,1,2000)==1);int error=-1;unsigned errlen=sizeof(error);assert(!dm_lan_socket_option(tcp,0xffff,0x1007,&error,&errlen,0)&&error==0);assert(!dm_lan_socket_fcntl(tcp,4,0));assert(dm_lan_socket_send(tcp,"hello",5,0)==5);assert(dm_lan_socket_recv(tcp,b,5,0x40)==5);assert(!memcmp(b,"world",5));assert(dm_lan_socket_recv(tcp,b,1,0)==0);assert(!dm_lan_socket_close(tcp));
    void*ai=NULL;assert(!dm_lan_getaddrinfo(ip,"123",NULL,&ai)&&ai);dm_lan_freeaddrinfo(ai);assert(dm_lan_getaddrinfo("battle.invalid","123",NULL,&ai)!=0&&ai==NULL);assert(!dm_lan_disconnect(0));assert(dm_lan_state()==4);assert(!dm_lan_close(0));assert(dm_lan_state()==1);dm_lan_finalize();printf("{\"client\":\"passed\"}\n");return 0;
}
static int lifecycle(void){setenv("DM_DR3_LAN","0",1);assert(dm_lan_initialize()==-1);assert(dm_lan_state()==0);assert(dm_lan_socket(2,2,0)==-1&&dm_lan_socket_errno()==100);setenv("DM_DR3_LAN","1",1);assert(!dm_lan_initialize());assert(!dm_lan_open(0));/* Refused nonblocking native TCP exposes EINPROGRESS=36 and SO_ERROR=61 on Apple;
 * the original guest table requires 115 and 111 respectively. */
uint16_t closedport;int reserve=bound(1,&closedport);assert(!dm_lan_socket_close(reserve));int refused=dm_lan_socket(2,1,0);assert(refused>=0);assert(!dm_lan_socket_fcntl(refused,4,0x800));uint8_t nowhere[16];address(nowhere,getenv("DM_LAN_BIND_IP"),closedport);int cr=dm_lan_socket_connect(refused,nowhere,16);assert(cr==-1&&(dm_lan_socket_errno()==115||dm_lan_socket_errno()==111));struct pollfd writefd={.fd=refused,.events=POLLOUT};assert(dm_lan_socket_poll(&writefd,1,2000)==1);int soerror=-1;unsigned errlen=sizeof(soerror);assert(!dm_lan_socket_option(refused,0xffff,0x1007,&soerror,&errlen,0));assert(soerror==111);assert(!dm_lan_socket_close(refused));
int fd=dm_lan_socket(2,2,0);assert(fd>=0);int64_t timeout[2]={1,345000},got[2]={-1,-1};unsigned n=16;assert(!dm_lan_socket_option(fd,0xffff,0x1006,timeout,&n,1));assert(!dm_lan_socket_option(fd,0xffff,0x1006,got,&n,0));assert(n==16&&got[0]==1&&got[1]>=345000&&got[1]<400000);timeout[1]=1000000;assert(dm_lan_socket_option(fd,0xffff,0x1006,timeout,&n,1)==-1);dm_lan_suspend(1);uint32_t ip,mask;assert(dm_lan_ipv4(&ip,&mask)==-1);assert(dm_lan_socket_close(fd)==-1&&dm_lan_socket_errno()==9);dm_lan_suspend(0);assert(!dm_lan_ipv4(&ip,&mask));assert(dm_lan_state()==4);assert(!dm_lan_close(0));int finalized=dm_lan_socket(2,2,0);assert(finalized>=0);dm_lan_finalize();assert(dm_lan_state()==0);assert(dm_lan_socket_close(finalized)==-1&&dm_lan_socket_errno()==9);assert(!dm_lan_initialize());assert(dm_lan_state()==1);dm_lan_finalize();puts("lifecycle passed");return 0;}
int main(int argc,char**argv){assert(argc==2);if(!strcmp(argv[1],"lifecycle"))return lifecycle();if(!strcmp(argv[1],"host")||!strcmp(argv[1],"destroyhost"))return host(!strcmp(argv[1],"destroyhost"));return client(!strcmp(argv[1],"destroyclient"),!strcmp(argv[1],"transitionclient"));}
