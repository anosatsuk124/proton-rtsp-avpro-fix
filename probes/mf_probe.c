#define COBJMACROS
#include <windows.h>
#include <initguid.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mfmediaengine.h>
#include <dxgiformat.h>
#include <stdio.h>

static HRESULT WINAPI qi(IMFMediaEngineNotify *self, REFIID id, void **out) {
    if (IsEqualIID(id, &IID_IUnknown) || IsEqualIID(id, &IID_IMFMediaEngineNotify)) {
        *out = self; return S_OK;
    }
    *out = NULL; return E_NOINTERFACE;
}
static ULONG WINAPI addref(IMFMediaEngineNotify *self) { return 2; }
static ULONG WINAPI release(IMFMediaEngineNotify *self) { return 1; }
static HRESULT WINAPI event(IMFMediaEngineNotify *self, DWORD id, DWORD_PTR p1, DWORD p2) {
    printf("EVENT %lu %llu %lu\n", id, (unsigned long long)p1, p2);
    fflush(stdout); return S_OK;
}
static IMFMediaEngineNotifyVtbl notify_vtbl = {qi, addref, release, event};
static IMFMediaEngineNotify notify = {&notify_vtbl};
#define CHECK(x) do { printf("CHECK %s\n", #x); fflush(stdout); HRESULT h=(x); if (FAILED(h)) { printf("FAIL %s %08lx\n", #x, h); fflush(stdout); return 1; } } while(0)

int wmain(int argc, wchar_t **argv) {
    if (argc != 2) { fputs("Usage: mf_probe URL\n", stderr); return 2; }
    setvbuf(stdout, NULL, _IONBF, 0);
    puts("PROBE START");
    IMFMediaEngineClassFactory *factory;
    IMFAttributes *attrs;
    IMFMediaEngine *engine;
    CHECK(CoInitializeEx(NULL, COINIT_MULTITHREADED));
    CHECK(MFStartup(MF_VERSION, MFSTARTUP_FULL));
    CHECK(CoCreateInstance(&CLSID_MFMediaEngineClassFactory, NULL, CLSCTX_INPROC_SERVER,
                          &IID_IMFMediaEngineClassFactory, (void **)&factory));
    CHECK(MFCreateAttributes(&attrs, 3));
    CHECK(IMFAttributes_SetUnknown(attrs, &MF_MEDIA_ENGINE_CALLBACK, (IUnknown *)&notify));
    CHECK(IMFAttributes_SetUINT32(attrs, &MF_MEDIA_ENGINE_VIDEO_OUTPUT_FORMAT, DXGI_FORMAT_B8G8R8A8_UNORM));
    CHECK(IMFMediaEngineClassFactory_CreateInstance(factory, MF_MEDIA_ENGINE_REAL_TIME_MODE, attrs, &engine));
    CHECK(IMFMediaEngine_SetVolume(engine, 0.0));
    BSTR url=SysAllocString(argv[1]);
    CHECK(IMFMediaEngine_SetSource(engine, url));
    SysFreeString(url);
    CHECK(IMFMediaEngine_SetAutoPlay(engine, TRUE));
    for (int i=0;i<20;i++) {
        Sleep(1000);
        DWORD w=0,h=0; LONGLONG pts=0;
        IMFMediaEngine_GetNativeVideoSize(engine,&w,&h);
        HRESULT tick=IMFMediaEngine_OnVideoStreamTick(engine,&pts);
        printf("STATE %d ready=%u net=%u paused=%d time=%.6f duration=%.6f video=%lux%lu tick=%08lx pts=%lld\n",
               i,IMFMediaEngine_GetReadyState(engine),IMFMediaEngine_GetNetworkState(engine),
               IMFMediaEngine_IsPaused(engine),IMFMediaEngine_GetCurrentTime(engine),
               IMFMediaEngine_GetDuration(engine),w,h,tick,pts);
        fflush(stdout);
        if (i==4) printf("PLAY %08lx\n", IMFMediaEngine_Play(engine));
    }
    IMFMediaEngine_Shutdown(engine);
    return 0;
}
