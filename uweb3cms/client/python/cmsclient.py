#!/bin/python3
import requests
from uweb3.connections import Connector
from uweb3 import model
from expiringdict import ExpiringDict

class Cmsclient(Connector):
  """The factory that we use to create cms connectors"""
  def __init__(self, config, options, request, debug=False):
    """Sets up the connecton to the CMS client"""
    self.options = options[self.Name()]
    self.server = self.options['server']
    self.apikey = self.options['apikey']
    self.cache = int(self.options.get('cacheage', 0))
    if self.cache:
      self.connection = CachedCmsConnection(self.server, self.apikey, self.cache, debug)
    else:
      self.connection = CmsConnection(self.server, self.apikey, debug)


class CmsConnection(object):
  """The actual interacting connector that talks to the cms"""
  def __init__(self, server, apikey, debug=False):
    self.server = server
    self.apikey = apikey
    self.debug = debug
    self.session = requests.Session()

  def Request(self, url, timeout=None):
    """Does the http work to reach the CMS"""
    if self.debug:
     print('CMS fetch: %s%s' % (self.server, url))
    try:
      request = self.session.get('%s%s' % (self.server, url),
          timeout=timeout,
          headers={'apikey': self.apikey})
      if request.status_code == 404:
        raise CmsNoSuchPath('Cannot find the requested object')
      data = request.json()
      if 'error' in data:
        raise CmsError(data['error'])
    except CmsException:
      raise
    except Exception as error:
      raise CmsCannotReachError(error)
    return data


class CachedCmsConnection(CmsConnection):

  def __init__(self, server, apikey, cacheage, debug=False, cachesize=100):
    self.cacheage = cacheage
    self.cache = ExpiringDict(max_len=cachesize, max_age_seconds=self.cacheage)
    self.invalidcache = ExpiringDict(max_len=cachesize, max_age_seconds=self.cacheage)

    super().__init__(server, apikey, debug)

  def Request(self, url, timeout=None):
    """Does the http work to reach the CMS"""
    if url in self.cache:
      return self.cache[url]

    if url in self.invalidcache:
      if self.invalidcache[url] and 'error' in self.invalidcache[url]:
        CmsError(self.invalidcache[url]['error'])
      raise CmsNoSuchPath('Cannot find the requested object')

    if self.debug:
      print('CMS fetch: %s%s' % (self.server, url))
    try:
      request = self.session.get('%s%s' % (self.server, url),
          timeout=timeout,
          headers={'apikey': self.apikey})
      if request.status_code == 404:
        self.invalidcache[url] = False
        raise CmsNoSuchPath('Cannot find the requested object')
      data = request.json()
      if 'error' in data:
        self.invalidcache[url] = data['error']
        raise CmsError(data['error'])
    except CmsException:
      raise
    except Exception as error:
      raise CmsCannotReachError(url, error)
    self.cache[url] = data
    return data


class Collection(model.BaseRecord):
  _CONNECTOR = 'cmsclient'

  @classmethod
  def FromPrimary(cls, connection, name):
    """Returns the collection"""
    url = '/json/collection/%s' % name
    try:
      collectiondata = connection.Request(url)
    except CmsNoSuchPath as error:
      raise CmsNoSuchCollection(error)
    #json dict keys are strings, we want Ints
    articlesdict = {}
    for articleId, article in collectiondata['articles'].items():
      articlesdict[int(articleId)] = article
    collectiondata['articles'] = articlesdict
    return cls(connection, collectiondata)

  def Menu(self, menu="main"):
    """Returns the articles in the menu."""
    for articleID in self['menus'][menu]:
      article = self['articles'][articleID['ID']]
      article['menuname'] = articleID['name']
      yield Article(self.connection, article)

  def ArticleByUrl(self, url):
    """Returns the article by url"""
    for article in self['articles']:
      if self['articles'][article]['url'] == url:
        return Article(self.connection, self['articles'][article])
    raise CmsNoSuchUrl('Url does not exists in this collection: %r' % url)

  def FirstArticle(self, menu='main'):
    firstarticle = self['menus'][menu][0]['ID']
    return Article(self.connection, self['articles'][firstarticle])

class Article(model.BaseRecord):
  _CONNECTOR = 'cmsclient'

  @classmethod
  def FromPrimary(cls, connection, name):
    """Returns the requested article if present"""
    url = '/json/article/%s' % name
    try:
      articledata = connection.Request(url)
      return cls(connection, articledata)
    except CmsNoSuchPath as error:
      raise CmsNoSuchArticle(error)


class CmsException(Exception):
  """Catchall error for errors in the CMS"""


class CmsCannotReachError(CmsException):
  """We are unable to reach the CMS server"""


class CmsError(Exception):
  """Cms server returned with an error."""


class CmsNoSuchPath(CmsException):
  """The requested Object does not exists"""


class CmsNoSuchCollection(CmsException):
  """The requested Collection does not exists"""


class CmsNoSuchUrl(CmsException):
  """The requested Url does not exists"""


class CmsNoSuchArticle(CmsException):
  """The requested Article does not exists"""
