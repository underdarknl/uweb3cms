"""WSGI script for Apache mod_wsgi

For more information about running and configuring mod_wsgi, please refer to
documentation at https://code.google.com/p/modwsgi/wiki/DeveloperGuidelines.
"""

# Add the current directory to site packages, this allows importing of the
# project. For production, installing this into a virtualenv is recommended.
import os
import site
#site.addsitedir('/path/to/virtualenv/site-packages')
site.addsitedir(os.path.dirname(__file__))

# Import the project and create a WSGI application object
import base
application = base.main()
