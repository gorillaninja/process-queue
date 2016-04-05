#!/usr/bin/env python

from process_queue import queue

queue.init()
path = queue.pick_input()

if path:
    queue.process_input(path)
