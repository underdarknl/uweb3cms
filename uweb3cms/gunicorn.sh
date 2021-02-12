#!/bin/bash
gunicorn3 -b :8000 'base:main()' --workers=4
