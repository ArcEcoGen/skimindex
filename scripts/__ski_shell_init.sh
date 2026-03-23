# ============================================================
# __ski_shell_init.sh
# Bash --init-file for the skimindex interactive shell.
#
# - Sources standard bash startup files
# - Loads skimindex config and exports SKIMINDEX__* env vars
# - Defines reload_config to re-read the config from scratch
#
# reload_config clears all SKIMINDEX__* variables before
# reloading, so the config file always takes precedence over
# any previously exported values.
#
# Source this file — do NOT execute it directly.
# ============================================================

# Load skimindex libraries first, before any profile that could reset PATH
source "${SKIMINDEX_SCRIPTS_DIR:-/app/scripts}/__skimindex.sh"

# Standard bash interactive startup
[[ -f /etc/profile ]] && source /etc/profile
[[ -f ~/.bashrc    ]] && source ~/.bashrc

# Re-ensure container tools take precedence after profile sourcing
export PATH="/app/bin:/app/scripts:${PATH}"

# reload_config
#   Unsets all SKIMINDEX__* variables and the config-loaded guard,
#   then re-sources __skimindex_config.sh so the TOML file wins.
reload_config() {
    local _var
    while IFS= read -r _var; do
        unset "$_var"
    done < <(compgen -e | grep '^SKIMINDEX__')
    unset _SKIMINDEX_CONFIG_LOADED
    # _skimindex_sh_dir is required by __skimindex_config.sh
    local _skimindex_sh_dir="${SKIMINDEX_SCRIPTS_DIR:-/app/scripts}"
    source "${_skimindex_sh_dir}/__skimindex_config.sh"
    loginfo "Configuration reloaded."
}
