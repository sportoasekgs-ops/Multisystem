import multiprocessing
import os

bind = "0.0.0.0:5000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 120
keepalive = 5

max_requests = 1000
max_requests_jitter = 50

errorlog = "-"
loglevel = "info"
accesslog = "-"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

preload_app = False

def on_starting(server):
    """Called just before the master process is initialized."""
    server.log.info("Starting SportOase Buchungssystem")

def on_reload(server):
    """Called to recycle workers during a reload via SIGHUP."""
    server.log.info("Reloading SportOase Buchungssystem")

def when_ready(server):
    """Called just after the server is started."""
    server.log.info("SportOase Buchungssystem is ready to serve requests")

def on_exit(server):
    """Called just before exiting Gunicorn."""
    server.log.info("Shutting down SportOase Buchungssystem")
