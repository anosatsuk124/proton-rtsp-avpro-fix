/* Minimal local AVPro host. No VRChat process injection or private DLL offsets. */
#define COBJMACROS
#include <windows.h>
#include <d3d11.h>
#include <stdio.h>
#include <math.h>
#undef GetCurrentTime

typedef struct { unsigned long long high,low; } UnityGUID;
static ID3D11Device *unityDevice;
static int __stdcall Renderer(void){return 2;}
static void __stdcall EventCallback(void *cb){(void)cb;}
static int __stdcall ReserveEvents(int count){(void)count;return 0;}
static void *graphics[]={Renderer,EventCallback,EventCallback,ReserveEvents};
static void *__stdcall D3DDevice(void){return unityDevice;}
static void *d3d[]={D3DDevice};
static void *__stdcall GetInterface(UnityGUID guid){
    if(guid.high==0x7CBA0A9CA4DDB544ULL && guid.low==0x8C5AD4926EB17B11ULL)return graphics;
    if(guid.high==0xAAB37EF87A87D748ULL && guid.low==0xBF76967F07EFB177ULL)return d3d;
    return NULL;
}
static void __stdcall RegisterInterface(UnityGUID guid,void *ptr){(void)guid;(void)ptr;}
static void *__stdcall GetInterfaceSplit(unsigned long long high,unsigned long long low){return GetInterface((UnityGUID){high,low});}
static void __stdcall RegisterInterfaceSplit(unsigned long long high,unsigned long long low,void *ptr){(void)high;(void)low;(void)ptr;}
static void *interfaces[]={GetInterface,RegisterInterface,GetInterfaceSplit,RegisterInterfaceSplit};
#define FN(ret,name,args) typedef ret (__cdecl *name##_fn) args; name##_fn name=(name##_fn)GetProcAddress(lib,#name); if(!name){fprintf(stderr,"Missing AVPro export: %s\n",#name);return 2;}
int wmain(int argc,wchar_t **argv) {
    if(argc!=5){fputs("Usage: avpro_probe AVPRO_DLL URL REPORT_NDJSON SECONDS\n",stderr);return 2;}
    int seconds=_wtoi(argv[4]);if(seconds<5 || seconds>120)return 2;
    FILE *report=_wfopen(argv[3],L"wb");if(!report){perror("report");return 2;}
    HMODULE lib=LoadLibraryW(argv[1]);
    if(!lib){fprintf(stderr,"AVPro LoadLibrary error %lu\n",GetLastError());return 3;}
    FN(void,UnityPluginLoad,(void*));
    FN(void,UnitySetGraphicsDevice,(void*,int,int));
    FN(unsigned char,Init,(BOOL));
    FN(const char*,GetPluginVersion,(void));
    FN(void*,BeginOpenSource,(void*,int,int,BOOL,BOOL,BOOL,BOOL,BOOL,BOOL,const wchar_t*,int,void**,unsigned,int,const wchar_t*,BOOL));
    FN(void*,EndOpenSource,(void*,const wchar_t*));
    FN(void,CloseSource,(void*));
    FN(void,Update,(void*));
    FN(void,EndUpdate,(void*));
    FN(void,UnityRenderEvent,(int));
    FN(void,Play,(void*));
    FN(void,SetPlaybackRate,(void*,float));
    FN(unsigned char,CanPlay,(void*));
    FN(unsigned char,IsPlaying,(void*));
    FN(unsigned char,HasMetaData,(void*));
    FN(unsigned char,IsBuffering,(void*));
    FN(unsigned char,IsPlaybackStalled,(void*));
    FN(unsigned char,IsFinished,(void*));
    FN(int,GetLastErrorCode,(void*));
    FN(long long,GetLastExtendedErrorCode,(void*));
    FN(int,GetWidth,(void*));
    FN(int,GetHeight,(void*));
    FN(int,GetTextureFrameCount,(void*));
    FN(void*,GetTexturePointer,(void*));
    FN(int,GrabAudio,(void*,float*,int,int));
    FN(double,GetDuration,(void*));
    FN(double,GetCurrentTime,(void*));
    ID3D11DeviceContext *context=NULL;D3D_FEATURE_LEVEL level;
    HRESULT hr=D3D11CreateDevice(NULL,D3D_DRIVER_TYPE_HARDWARE,NULL,D3D11_CREATE_DEVICE_BGRA_SUPPORT,NULL,0,D3D11_SDK_VERSION,&unityDevice,&level,&context);
    if(FAILED(hr)){fprintf(stderr,"D3D11CreateDevice %08lx\n",hr);return 3;}
    UnityPluginLoad(interfaces);UnitySetGraphicsDevice(unityDevice,2,0);
    if(!Init(TRUE)){fputs("AVPro Init failed\n",stderr);return 3;}
    UnitySetGraphicsDevice(unityDevice,2,0);
    printf("AVPro native version: %s\n",GetPluginVersion());fflush(stdout);
    const char *version=GetPluginVersion();
    fputs("{\"native_version\":\"",report);
    for(const char *p=version;*p;p++)if((*p>='0'&&*p<='9')||(*p>='A'&&*p<='Z')||(*p>='a'&&*p<='z')||*p=='.'||*p=='-')fputc(*p,report);
    fputs("\"}\n",report);fflush(report);
    void *instance=BeginOpenSource(NULL,0,1,FALSE,TRUE,FALSE,FALSE,FALSE,FALSE,L"",48000,NULL,0,0,L"",FALSE);
    if(!instance || !(instance=EndOpenSource(instance,argv[2]))){fputs("AVPro open failed\n",stderr);return 4;}
    SetPlaybackRate(instance,1.0f);
    float samples[2048];int played=0,error=0;unsigned long long grabbed=0;double peak=0;
    ULONGLONG start=GetTickCount64(),nextReport=start;
    while(GetTickCount64()-start<(ULONGLONG)seconds*1000){
        MSG msg;while(PeekMessageW(&msg,NULL,0,0,PM_REMOVE)){TranslateMessage(&msg);DispatchMessageW(&msg);}
        Update(instance);UnityRenderEvent(0);UnityRenderEvent(1);GetTexturePointer(instance);
        ZeroMemory(samples,sizeof(samples));int count=GrabAudio(instance,samples,2048,2);
        if(count>0){grabbed+=(unsigned)count;for(int i=0;i<2048;i++){double x=fabs(samples[i]);if(x>peak)peak=x;}}
        EndUpdate(instance);
        ULONGLONG now=GetTickCount64();
        error=GetLastErrorCode(instance);
        if(now>=nextReport || error){
            double duration=GetDuration(instance),time=GetCurrentTime(instance);
            fprintf(report,"{\"elapsed\":%.3f,\"metadata\":%u,\"canplay\":%u,\"playing\":%u,\"buffering\":%u,\"stalled\":%u,\"finished\":%u,\"error\":%d,\"extended_error\":%lld,\"width\":%d,\"height\":%d,\"frames\":%d,\"time\":%.6f,\"live\":%s,\"duration\":%.6f,\"audio_samples\":%llu,\"audio_peak\":%.6f}\n",
                (now-start)/1000.0,HasMetaData(instance),CanPlay(instance),IsPlaying(instance),IsBuffering(instance),IsPlaybackStalled(instance),IsFinished(instance),error,GetLastExtendedErrorCode(instance),GetWidth(instance),GetHeight(instance),GetTextureFrameCount(instance),isfinite(time)?time:0.0,isinf(duration)?"true":"false",isfinite(duration)?duration:0.0,grabbed,peak);
            fflush(report);nextReport=now+100;
        }
        if(CanPlay(instance)&&!played){Play(instance);played=1;}
        if(error)break;
        Sleep(16);
    }
    fprintf(report,"{\"probe_completed\":true,\"exit_error\":%d}\n",error);fflush(report);
    CloseSource(instance);fclose(report);
    ID3D11DeviceContext_Release(context);ID3D11Device_Release(unityDevice);
    return error?5:0;
}
