#!/usr/bin/python3
"""The Router for the CMSaas application."""
__version__ = '1.0.1'
__author__ = ('Jan Klopper <jan@underdark.nl>',
              'Arjen Pander <arjen@underdark.nl>')

# standard modules
import os

# Third-party modules
import uweb3

# Application
from . import pages

def main():
  """Creates a uWeb3 application.

  The application is created from the following components:

  - The presenter class (PageMaker) which implements the request handlers.
  - The routes iterable, where each 2-tuple defines a url-pattern and the
    name of a presenter method which should handle it.
  - The execution path, internally used to find templates etc.
  """
  return uweb3.uWeb(pages.PageMaker,
      [('/', 'RequestIndex'),

       # login / user management
       ('/login', 'HandleLogin', 'POST'),
       ('/login', 'RequestLogin'),
       ('/logout', 'RequestLogout'),
       ('/usersettings', 'RequestUserSettings'),
       ('/apikeys', 'RequestApiKeys'),
       ('/resetpassword', 'RequestResetPassword'),
       ('/resetpassword/([^/]*)/(.*)', 'RequestResetPassword'),

       # html layout
       ('/atom/([\d]+)', 'RequestAtomExample'),

       ('/article/([\w\-\.]+)/([\w\-\. ]+)', 'RequestArticle',  'GET'),
       ('/article/([\w\-\. ]+)', 'RequestArticle', 'GET'),
       ('/collection/([\w\-\.]+)', 'RequestCollection', 'GET'),
       ('/collectionarticles', 'RequestCollectionArticles', 'POST'),
       ('/collection', 'RequestCollectionNew', 'POST'),
       ('/collection/([\w\-\.]+)/remove', 'RequestCollectionRemove', 'POST'),
       ('/collection/([\w\-\.]+)', 'RequestCollectionSave', 'POST'),

       ('/menus', 'RequestMenus'),
       ('/menu/([\w\-\.]+)/([\w\-\.]+)/remove', 'RequestMenuRemove', 'POST'),
       ('/menuarticles', 'RequestMenuArticles', 'POST'),
       ('/menu/([\w\-\.]+)/([\w\-\.]+)', 'RequestMenuSave', 'POST'),
       ('/menu/([\w\-\.]+)/([\w\-\.]+)', 'RequestMenu'),
       ('/menu', 'RequestMenuNew', 'POST'),

       ('/articles', 'RequestArticles'),
       ('/article', 'RequestArticleNew', 'POST'),
       ('/article/([\w\-\. ]+)', 'RequestArticleSave', 'POST'),
       ('/article/([\w\-\. ]+)/remove', 'RequestArticleRemove', 'POST'),

       ('/variables', 'RequestVarsSave', 'POST'),
       ('/variables', 'RequestVariables'),

       ('/type', 'RequestTypeNew', 'POST'),
       ('/types', 'RequestTypes'),
       ('/type/([\w\-\.]+)/remove', 'RequestTypeRemove', 'POST'),
       ('/type/([\w\-\.]+)', 'RequestTypeSave', 'POST'),
       ('/type/([\w\-\.]+)', 'RequestType', 'GET'),
       ('/typearticles/([\w\-\.]+)', 'RequestTypeArticles', 'GET'),

       # JSON layout
       ('/json/article/([\w\-\. ]+)/?(.+)?', 'RequestArticleJson'),
       ('/json/collection/([\w\-_\.]+)', 'RequestCollectionJson'),
       ('/json/menu/([\w\-\.]+)/([\w\-\.]+)', 'RequestMenuJson'),

       ('/setup', 'RequestSetup'),
       ('/admin', 'RequestAdmin'),

       # Helper files
       ('(/styles/.*)', 'Static'),
       ('(/js/.*)', 'Static'),
       ('(/media/.*)', 'Static'),
       ('(/favicon.ico)', 'Static'),
       ('(/.*)', 'RequestInvalidcommand')],
      os.path.dirname(__file__)
  )
