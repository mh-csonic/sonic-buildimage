# PersonaForge runtime package used by native config/show commands.
SONIC_PERSONAFORGE_VERSION = 0.1.0
SONIC_PERSONAFORGE_NAME = sonic_personaforge
SONIC_PERSONAFORGE = $(SONIC_PERSONAFORGE_NAME)-$(SONIC_PERSONAFORGE_VERSION)-py3-none-any.whl
$(SONIC_PERSONAFORGE)_SRC_PATH = $(SRC_PATH)/personaforge
$(SONIC_PERSONAFORGE)_PYTHON_VERSION = 3
$(SONIC_PERSONAFORGE)_NAME = $(SONIC_PERSONAFORGE_NAME)
$(SONIC_PERSONAFORGE)_VERSION = $(SONIC_PERSONAFORGE_VERSION)
SONIC_PYTHON_WHEELS += $(SONIC_PERSONAFORGE)

# PersonaForge build specialization is inert unless a profile is selected.
PERSONAFORGE_PROFILE ?=

ifneq ($(strip $(PERSONAFORGE_PROFILE)),)
personaforge_shell_quote = '$(subst ','"'"',$(1))'
PERSONAFORGE_PROFILE_VALID := $(shell printf '%s' $(call personaforge_shell_quote,$(PERSONAFORGE_PROFILE)) | grep -Eq '^[a-z0-9]([-a-z0-9]*[a-z0-9])?$$' && echo y)
ifneq ($(PERSONAFORGE_PROFILE_VALID),y)
$(error Invalid PERSONAFORGE_PROFILE '$(PERSONAFORGE_PROFILE)')
endif

PERSONAFORGE_PROFILE_FILE := personaforge/profiles/$(PERSONAFORGE_PROFILE).yaml
PERSONAFORGE_CATALOG_FILE := src/personaforge/catalogs/202605.yaml
PERSONAFORGE_GENERATOR := scripts/personaforge-build
PERSONAFORGE_SOURCE_COMMIT := $(shell git rev-parse HEAD 2>/dev/null)
PERSONAFORGE_PLATFORM := $(if $(CONFIGURED_PLATFORM),$(CONFIGURED_PLATFORM),unspecified)

ifeq ($(wildcard $(PERSONAFORGE_PROFILE_FILE)),)
$(error Unknown PERSONAFORGE_PROFILE '$(PERSONAFORGE_PROFILE)')
endif

PERSONAFORGE_BUILD_KEY := $(shell PYTHONPATH=$(CURDIR)/src/personaforge python3 $(PERSONAFORGE_GENERATOR) key \
	--profile $(call personaforge_shell_quote,$(PERSONAFORGE_PROFILE_FILE)) --catalog $(call personaforge_shell_quote,$(PERSONAFORGE_CATALOG_FILE)) \
	--source-commit $(call personaforge_shell_quote,$(PERSONAFORGE_SOURCE_COMMIT)) --platform $(call personaforge_shell_quote,$(PERSONAFORGE_PLATFORM)) \
	2>/dev/null || echo __PERSONAFORGE_ERROR__)
ifeq ($(PERSONAFORGE_BUILD_KEY),__PERSONAFORGE_ERROR__)
$(error PersonaForge profile validation failed for '$(PERSONAFORGE_PROFILE)'; run $(PERSONAFORGE_GENERATOR) directly for details)
endif

PERSONAFORGE_OUTPUT_DIR := target/personaforge/generated/$(PERSONAFORGE_PROFILE)/$(PERSONAFORGE_BUILD_KEY)
PERSONAFORGE_MAKE_FILE := $(PERSONAFORGE_OUTPUT_DIR)/personaforge.mk
PERSONAFORGE_INPUTS := $(PERSONAFORGE_PROFILE_FILE) $(PERSONAFORGE_CATALOG_FILE) $(PERSONAFORGE_GENERATOR) \
	$(wildcard src/personaforge/personaforge/*.py) $(wildcard src/personaforge/schema/*.json)

$(PERSONAFORGE_MAKE_FILE): $(PERSONAFORGE_INPUTS)
	@mkdir -p $(@D)
	@PYTHONPATH=$(CURDIR)/src/personaforge python3 $(PERSONAFORGE_GENERATOR) generate \
		--profile $(call personaforge_shell_quote,$(PERSONAFORGE_PROFILE_FILE)) --catalog $(call personaforge_shell_quote,$(PERSONAFORGE_CATALOG_FILE)) \
		--source-commit $(call personaforge_shell_quote,$(PERSONAFORGE_SOURCE_COMMIT)) --platform $(call personaforge_shell_quote,$(PERSONAFORGE_PLATFORM)) \
		--config-user rules/config.user --output-dir $(call personaforge_shell_quote,$(@D))

include $(PERSONAFORGE_MAKE_FILE)
endif
