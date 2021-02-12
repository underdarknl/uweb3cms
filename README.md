# µWeb3 CMS as a service

# How to run

* Run `serve.py` from the commandline
* Run `gunicorn.sh.py` from the commandline for running on Gunicorn
* Use the included `base.wsgi` script to set up Apache + mod_wsgi

The base/config.ini holds the database passwords and login
A secret key will be generated on first boot and writen to the config.ini file
by the server, it needs to be writeable.

# Setup the database

Import schema/schema.sql
Optionally import schema/types.sql to insert some basic atom types.

# how to create a login

Navigate to /setup and you will be presented a form to setup the config and
first admin account.

# Data layout

The idea is that data is stored in 'atoms', these atoms are made up of 'fields'
which the cms user can fill out.
Atoms are combined into articles. Articles usually represent one webpage.
Articles are then combined into collections, which usually represent one
website.

# Advanced usage

A designer might re-use the same parts of content on all or most pages on the
website, instead of adding the same atom to all articles, it would be more wise
to setup a seperate article which is loaded for each webpage that requires these
shared parts. For example, a footer might be shared on all pages, and can be
edited in one location

# Sharing articles

Sharing articles between collections allows for multiple websites to use the
same content. This works best for boiler plate pages like disclaimers, privacy
statements, or contact pages, as they will share the same texts anyway.

# Using variables

There are three levels of variables which you can use.
First there's the global variables. These can be set in the cms, and then used
in any atom field. The value to which the variable is set will be shown on the
location where the variable is used.

The second level is the cacheable variables that the client pushed to the cms.
These variables are designed to be cached on a collection basis by the client.
These might be used to set for example the website name in a contact page, as
all requests for this collection will use the same name, it only needs to be
replaced once, and can be cached for speed after that.

The third level is the uncacheable variables. These are pushed by the client,
for every request and should not be cached as they might contain stuff that is
only valid for the current web-request, eg, is someone logged in? or the user's
name, or the current date and time.
