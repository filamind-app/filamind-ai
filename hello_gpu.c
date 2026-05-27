/*
 * Hello GPU - SaynologyAI prototype
 * Uses dlopen to load libnvidia-ml.so at runtime — no NVML headers needed.
 * Validates that a cross-compiled binary can call NVIDIA libraries on DSM.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>

typedef int (*nvmlInit_t)(void);
typedef int (*nvmlShutdown_t)(void);
typedef int (*nvmlDeviceGetCount_t)(unsigned int*);
typedef int (*nvmlDeviceGetHandleByIndex_t)(unsigned int, void**);
typedef int (*nvmlDeviceGetName_t)(void*, char*, unsigned int);
typedef int (*nvmlSystemGetDriverVersion_t)(char*, unsigned int);
typedef int (*nvmlSystemGetCudaDriverVersion_t)(int*);
typedef int (*nvmlDeviceGetMemoryInfo_t)(void*, void*);

struct memInfo {
    unsigned long long total;
    unsigned long long free;
    unsigned long long used;
};

int main(void) {
    printf("=== SaynologyAI Hello GPU prototype ===\n");
    printf("Loading libnvidia-ml.so.1...\n");

    void* h = dlopen("libnvidia-ml.so.1", RTLD_LAZY);
    if (!h) {
        fprintf(stderr, "FAIL: %s\n", dlerror());
        return 1;
    }
    printf("OK: NVML library loaded\n");

    nvmlInit_t                       nvmlInit       = (nvmlInit_t)dlsym(h, "nvmlInit_v2");
    nvmlShutdown_t                   nvmlShutdown   = (nvmlShutdown_t)dlsym(h, "nvmlShutdown");
    nvmlDeviceGetCount_t             getCount       = (nvmlDeviceGetCount_t)dlsym(h, "nvmlDeviceGetCount_v2");
    nvmlDeviceGetHandleByIndex_t     getHandle      = (nvmlDeviceGetHandleByIndex_t)dlsym(h, "nvmlDeviceGetHandleByIndex_v2");
    nvmlDeviceGetName_t              getName        = (nvmlDeviceGetName_t)dlsym(h, "nvmlDeviceGetName");
    nvmlSystemGetDriverVersion_t     getDriverVer   = (nvmlSystemGetDriverVersion_t)dlsym(h, "nvmlSystemGetDriverVersion");
    nvmlSystemGetCudaDriverVersion_t getCudaVer     = (nvmlSystemGetCudaDriverVersion_t)dlsym(h, "nvmlSystemGetCudaDriverVersion");
    nvmlDeviceGetMemoryInfo_t        getMem         = (nvmlDeviceGetMemoryInfo_t)dlsym(h, "nvmlDeviceGetMemoryInfo");

    if (!nvmlInit || !getCount || !getHandle || !getName) {
        fprintf(stderr, "FAIL: missing required NVML symbols\n");
        return 2;
    }

    int rc = nvmlInit();
    if (rc != 0) {
        fprintf(stderr, "FAIL: nvmlInit returned %d\n", rc);
        return 3;
    }
    printf("OK: NVML initialized\n");

    char driver[128] = {0};
    if (getDriverVer) getDriverVer(driver, sizeof(driver));
    int cudaVer = 0;
    if (getCudaVer) getCudaVer(&cudaVer);
    printf("Driver: %s\n", driver);
    printf("CUDA version: %d.%d\n", cudaVer/1000, (cudaVer%1000)/10);

    unsigned int count = 0;
    if (getCount(&count) != 0) { fprintf(stderr, "FAIL: getCount\n"); return 4; }
    printf("GPU count: %u\n", count);

    for (unsigned int i = 0; i < count; i++) {
        void* dev = NULL;
        if (getHandle(i, &dev) != 0) continue;
        char name[128] = {0};
        getName(dev, name, sizeof(name));
        printf("  [%u] %s\n", i, name);
        if (getMem) {
            struct memInfo mi = {0};
            if (getMem(dev, &mi) == 0) {
                printf("      VRAM: %llu MB total, %llu MB free\n",
                       mi.total / (1024*1024), mi.free / (1024*1024));
            }
        }
    }

    nvmlShutdown();
    dlclose(h);
    printf("=== SUCCESS ===\n");
    return 0;
}
