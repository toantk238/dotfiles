claude_hooks_log() {
  if exists tspin; then
    tspin -f ~/.claude/hooks/stop_router.log
  elif 
    tail -f ~/.claude/hooks/stop_router.log
}
