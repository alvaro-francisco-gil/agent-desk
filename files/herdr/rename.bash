# Sourced from ~/.bashrc. Alt+R types "/rename " (ghostty and foot), which Claude
# takes as its own command; in a herdr shell it names the pane and its tab, the
# name the agents panel shows for a shell opened with Alt+Enter.
if [[ -n ${HERDR_PANE_ID:-} && -n ${HERDR_TAB_ID:-} ]]; then
  function /rename {
    if (($# == 0)); then
      echo "usage: /rename <name>" >&2
      return 2
    fi
    # The leading blank braille cell matches new-terminal.py's indent.
    herdr pane rename "$HERDR_PANE_ID" $'\u2800 '"$*" >/dev/null && herdr tab rename "$HERDR_TAB_ID" "$*" >/dev/null
  }
fi
