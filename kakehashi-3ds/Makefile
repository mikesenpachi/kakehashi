#---------------------------------------------------------------------------------
# kakehashi 3DS plugin. Based on the CTRPluginFramework TestPlugin Makefile, release build only.
# Build with Docker from the repo root: make 3ds
#---------------------------------------------------------------------------------
.SUFFIXES:

ifeq ($(strip $(DEVKITARM)),)
$(error "Please set DEVKITARM in your environment. export DEVKITARM=<path to>devkitARM")
endif

export TOPDIR ?= $(CURDIR)
include $(DEVKITARM)/3ds_rules

CTRPFLIB	?=	$(DEVKITPRO)/libctrpf

TARGET		:=	kakehashi
SOURCES		:=	Sources
PSF		:=	kakehashi.plgInfo

ARCH		:=	-march=armv6k -mtune=mpcore -mfloat-abi=hard -mtp=soft
CFLAGS		:=	-mword-relocations -ffunction-sections -fdata-sections -fno-strict-aliasing \
			-Wall -DNDEBUG=1 -O2 -fomit-frame-pointer $(ARCH) $(INCLUDE) -D__3DS__
CXXFLAGS	:=	$(CFLAGS) -fno-rtti -fno-exceptions -std=gnu++17
ASFLAGS		:=	$(ARCH)
LDFLAGS		:=	-T $(TOPDIR)/3gx.ld $(ARCH) -Os \
			-Wl,--strip-discarded,--strip-debug,--gc-sections,--section-start,.text=0x07000100
LIBS		:=	-lctrpf -lctru -lm
LIBDIRS		:=	$(CTRPFLIB) $(CTRULIB) $(PORTLIBS)

ifneq ($(notdir $(CURDIR)),build)
#---------------------------------------------------------------------------------
export VPATH	:=	$(foreach dir,$(SOURCES),$(CURDIR)/$(dir))
export DEPSDIR	:=	$(CURDIR)/build
CPPFILES	:=	$(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.cpp)))
export LD	:=	$(CXX)
export OFILES	:=	$(CPPFILES:.cpp=.o)
export INCLUDE	:=	-I$(CURDIR)/Includes $(foreach dir,$(LIBDIRS),-I$(dir)/include) -I$(CURDIR)/build
export LIBPATHS	:=	$(foreach dir,$(LIBDIRS),-L $(dir)/lib)

.PHONY: all clean

all:
	@mkdir -p build
	@$(MAKE) OUTPUT=$(CURDIR)/$(TARGET).3gx --no-print-directory -C build -f $(CURDIR)/Makefile

clean:
	@rm -fr build $(TARGET).elf $(TARGET).3gx

#---------------------------------------------------------------------------------
else
#---------------------------------------------------------------------------------
DEPENDS	:=	$(OFILES:.o=.d)

$(OUTPUT) : $(basename $(OUTPUT)).elf
$(basename $(OUTPUT)).elf : $(OFILES)

%.3gx: %.elf
	@echo creating $(notdir $@)
	@3gxtool -s $^ $(TOPDIR)/$(PSF) $@

-include $(DEPENDS)
#---------------------------------------------------------------------------------
endif
