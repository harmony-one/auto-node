#!/bin/bash
if tmux list-sessions | grep node ; then
  tmux a -t node
else
  echo ""
  cat /root/run.log
fi