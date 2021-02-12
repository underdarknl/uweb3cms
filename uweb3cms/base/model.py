#!/usr/bin/python3
"""Database abstraction model for the CMS."""

__author__ = 'Jan Klopper <janklopper@underdark.nl>'
__version__ = '2.0'

# standard modules
import datetime
import pytz
import re
import json
from marko.ext.gfm import gfm as markdown
from uweb3.libs.safestring import HTMLsafestring

# Custom modules
from uweb3 import model
from passlib.hash import pbkdf2_sha256
import secrets

NOTDELETEDDATE = '1000-01-01 00:00:00'
NOTDELETED = 'dateDeleted = "%s"' % NOTDELETEDDATE
DEFAULTMENUNAME = 'main'

class SanitizedRecord(model.Record):
  def _Clean(self):
    pass

  def _PreCreate(self, cursor):
    self._Clean()
    super()._PreCreate(cursor)

  def _PreSave(self, cursor):
    self._Clean()
    super()._PreSave(cursor)

class Collection(SanitizedRecord):
  """Abstraction for the CMS collection model.

  For the collection, load the articles
  """

  @classmethod
  def Search(cls, connection, conditions=None, query=None):
    """Returns the articles matching the search

      Arguments:
      @ connection: sqltalk.connection
        Database connection to use.
      % query: str
        Filters on name
    """
    return cls.List(
      connection,
      conditions=['name like "%%%s%%"' % connection.EscapeValues(query)[1:-1],
                  NOTDELETED] + (conditions or []),
      order=[('collection.dateCreated', True)])

  @classmethod
  def FromName(cls, connection, name, conditions=None):
    """Returns the collection of the given common name.

    Arguments:
      @ connection: sqltalk.connection
        Database connection to use.
      @ name: str
        The common name of the collection.

    Raises:
      NotExistError:
        The given collection name does not exist.

    Returns:
      Collection: collection abstraction class.
    """
    safe_name = connection.EscapeValues(name)
    with connection as cursor:
      collection = cursor.Select(table=cls.TableName(),
                                 conditions=['name=%s' % safe_name,
                                             NOTDELETED] + (conditions or []))
    if not collection:
      raise cls.NotExistError(
          'There is no collection with common name %r' % name)
    return cls(connection, collection[0])

  @classmethod
  def List(cls, *args, **kwargs):
    """Yields a Record object for every table entry."""
    kwargs['conditions'] = [NOTDELETED] + kwargs['conditions']
    if 'order' not in kwargs:
      kwargs['order'] = [('dateCreated', False)]
    return super().List(*args, **kwargs)

  @classmethod
  def ReverseList(cls, *args, **kwargs):
    """Yields a Record object for every table entry in reverse order."""
    if 'order' in kwargs:
      kwargs['order'] = [('dateCreated', True)] + kwargs['order']
    else:
      kwargs['order'] = [('dateCreated', True)]
    return cls.List(*args, **kwargs)

  def Articles(self, conditions=None, order=None, limit=None):
    """Yields all the articles for this collection."""
    with self.connection as cursor:
      articles = cursor.Select(
          table=('collectionArticle', 'article'),
          conditions=['collection=%d' % self['ID'],
                      'collectionArticle.article=article.ID',
                      'article.%s' % NOTDELETED] + (conditions or []),
          order=[['sortorder', False]] + (order or []),
          limit=limit)
    if not articles:
      raise self.NotExistError('There are no articles for this collection')
    for article in articles:
      yield Article(self.connection, article)

  def TopArticles(self, conditions=None, limit=None):
    """Returns the most used articles."""
    with self.connection as cursor:
      articles = cursor.Execute("""SELECT
          count(menuArticle.article) as count,
          article.*
        FROM
          `menuArticle`,
          `article`,
          `menu`
        WHERE
          menuArticle.article = article.ID and
          menuArticle.menu = menu.ID and
          article.%s and
          menu.collection = %d and
          menu.%s
          %s
        GROUP BY
          menuArticle.article
        ORDER BY
           count DESC
        %s""" %
           (NOTDELETED, self.key, NOTDELETED,
           'and %s' % ' and '.join(conditions) if conditions else '',
           ('LIMIT %d' % limit if limit else '')))
    for article in articles:
      yield Article(self.connection, article)

  def ArticleSearch(self, query):
    """Searches the article table for the collection."""
    return Article.Search(self.connection,
        conditions=['collection=%d' % self],
        query=query)

  def AddArticles(self, articles):
    """Adds the given list of article IDs to this collection."""
    # filter out non numeric input
    try:
      articles = list(map(int, articles))
    except ValueError:
      return False  # This prevents SQL injection.
    # filter out non existant articles
    articles = list(Article.List(self.connection,
        fields=(Article._PRIMARY_KEY, 'name'),
        conditions=('%s in (%s)' % (Article._PRIMARY_KEY, ','.join(map(str, articles))),
                    'client = %d' % self['client']), distinct=True))
    # what remains is a unique set of valid articles, which we can add
    if not articles:
      return False
    with self.connection as cursor:
      maxsort = cursor.Select(table='collectionArticle',
                              conditions='collection=%d' % self,
                              fields='max(sortorder) as max',
                              escape=False)
      sort = 0
      if maxsort and maxsort[0]['max'] is not None:
        sort = maxsort[0]['max'] + 1

      for article in articles:
        try:
          cursor.Insert(table='collectionArticle',
                        values={'collection': self.key,
                                'article': article['ID'],
                                'sortorder': sort,
                                'url': '%s_%s' % (self['name'], article['name'])})
          sort += 1
        except self.connection.IntegrityError:
          # was aleady present for this collection
          pass
    return True

  def Menus(self):
    """Returns the menu's that belong to this collection."""
    return self._Children(Menu)

  def Delete(self):
    """Overwrites the default Delete and sets the dateDeleted datetime instead"""
    self['dateDeleted'] = str(pytz.utc.localize(
        datetime.datetime.utcnow()))[0:19]
    self.Save()

  def Menu(self, menu):
    """Returns the menu object as referenced from this collection"""
    return Menu.FromNameAndCollection(self.connection, self.key, menu)

  def Article(self, article):
    """Returns the article object as referenced from this collection"""
    return Article.FromNameAndCollection(self.connection, self.key, article)

  @classmethod
  def Create(cls, connection, data, **attrs):
    """Intercept the collection creation to also make the Default menu"""
    collection = super().Create(connection, data, **attrs)
    Menu.Create(connection, {'name': DEFAULTMENUNAME,
                             'collection': collection.key,
                             'client': collection['client']})
    return collection

  def _Clean(self):
    if not self['name']:
      raise InvalidNameError('Provide a valid name')
    self['name'] = re.search('([\w\-_\.,]+)',
        self['name'].replace(' ', '_')).groups()[0][:80]
    if not self['name']:
      raise InvalidNameError('Provide a valid name')


class Article(SanitizedRecord):
  """Abstraction for the CMS article model."""

  @classmethod
  def Search(cls, connection, conditions=None, query=None):
    """Returns the articles matching the search

      Arguments:
      @ connection: sqltalk.connection
        Database connection to use.
      % query: str
        Filters on name
    """
    if query:
      conditions += [NOTDELETED,
                     'name like "%%%s%%"' % connection.EscapeValues(query)[1:-1]]
    return cls.List(connection, conditions=conditions)

  @classmethod

  def FromName(cls, connection, name, conditions=None):
    """Returns the Article of the given common name.

    Arguments:
      @ connection: sqltalk.connection
        Database connection to use.
      @ name: str
        The common name of the article.
      % load_foreign: bool ~~ True
        Flags loading of foreign key objects for the resulting article.

    Raises:
      NotExistError:
        The given article name does not exist.

    Returns:
      Article: article abstraction class.
    """
    safe_name = connection.EscapeValues(name)
    with connection as cursor:
      article = cursor.Select(table=cls.TableName(),
                              conditions=['name=%s' % safe_name,
                                          NOTDELETED] + (conditions or []))
    if not article:
      raise cls.NotExistError(
          'There is no article with common name %r' % name)
    return cls(connection, article[0])

  @classmethod
  def FromNameAndCollection(cls, connection, collection, article):
    """Returns the Article of the given common name for a given collection.

    Arguments:
      @ connection: sqltalk.connection
        Database connection to use.
      @ collection: int
        The  id of the collection.
      @ article: str
        The common name of the article.

    Raises:
      NotExistError:
        The given article name does not exist.

    Returns:
      Article: article abstraction class.
    """
    safe_article = connection.EscapeValues(article)
    with connection as cursor:
      article = cursor.Select(
          fields=('article.ID', 'article.name', 'article.published',
                  'collectionArticle.template',
                  'collectionArticle.meta'),
          table=('article', 'collectionArticle', 'collection'),
          conditions=('article.name=%s' % safe_article,
                      'article.ID=collectionArticle.article',
                      'collectionArticle.collection=collection.ID',
                      'collection.ID=%d' % collection,
                      'article.%s' % NOTDELETED,
                      'collection.%s' % NOTDELETED))
    if not article:
      raise cls.NotExistError(
          'There is no article with name: %s in collection: %s' % (article, collection))
    return cls(connection, article[0])

  @classmethod
  def FromPrimaryAndClient(cls, connection, pkey_value, client):
    """Returns the article requested if it belongs to a client."""
    article = list(cls.List(connection,
        fields=('article.*'),
        tables=('article'),
        conditions=('ID = %d' % pkey_value,
                    'client = %d' % client)))
    if article:
      return article[0]
    raise cls.NotExistError('Unable to load article %r' % pkey_value)

  @classmethod
  def FromClientAndType(cls, connection, typepkey, client, conditions=None, query=None):
    """Returns the articles requested if it belongs to a client and the given type
    ."""
    if not conditions:
      conditions = []
    conditions.extend(('atom.type = %d' % typepkey,
                       'articleAtom.article=article.ID',
                       'articleAtom.atom=atom.ID',
                       'article.client = %d' % client,
                       'article.%s' % NOTDELETED))
    if query:
      conditions.append('article.name like "%%%s%%"' %
          connection.EscapeValues(query)[1:-1])
    articles = list(cls.List(connection,
        fields=('article.*'),
        tables=('article', 'atom', 'articleAtom'),
        conditions=conditions))
    if not articles:
      raise cls.NotExistError('No articles for type %r' % typepkey)
    for article in articles:
      yield(cls(connection, article))

  def Atoms(self):
    """Get all atoms for this article"""
    with self.connection as cursor:
      atoms = cursor.Select(
          fields=('atom.*', 'articleAtom.sortorder'),
          table=('articleAtom', 'atom'),
          conditions=('article=%d' % self['ID'],
                      'articleAtom.atom=atom.ID'),
          order=[['sortorder', False]])
    if not atoms:
      raise self.NotExistError(
          'There are no atoms for this article')
    for atom in atoms:
      yield Atom(self.connection, atom)

  def AddToCollection(self, collection):
    """Adds the current article to the given collection"""
    if isinstance(collection, str):
      collection = Collection.FromName(self.connection, collection)
    with self.connection as cursor:
      sortinfo = cursor.Select(table='collectionArticle',
                           conditions='collection=%d' % collection,
                           fields='max(sortorder)',
                           escape=False)
      sort = 0
      try:
        if sortinfo[0][0] is not None:
          sort = sortinfo[0][0] + 1
      except Exception:
        pass

      cursor.Insert(table='collectionArticle',
                    values={'collection': collection.key,
                            'article': self['ID'],
                            'sortorder': sort})

  def RemoveFromCollection(self, collection):
    """Removes this article from the given collection."""
    with self.connection as cursor:
      cursor.Delete(table='collectionArticle',
                    conditions=('collection=%d' % collection,
                                'article=%d' % self.key))
    return True

  def RemoveFromMenu(self, menu):
    """Removes this article from the given menu."""
    with self.connection as cursor:
      cursor.Delete(table='menuArticle',
                    conditions=('menu=%d' % menu,
                                'article=%d' % self.key))
    return True

  def GetCollections(self):
    """Yields all collections this article is part of."""
    with self.connection as cursor:
      collections = cursor.Select(
        table=('collectionArticle', 'collection'),
        fields=('collection.ID', 'collection.name',
                'collection.dateCreated', 'collectionArticle.url'),
        conditions=('article=%d' % self.key,
                    'collection.ID=collectionArticle.collection',
                    'collection.%s' % NOTDELETED),
        order=[('collection.dateCreated', True)])
    for collection in collections:
      yield Collection(self.connection, collection)

  @classmethod
  def TopArticles(cls, connection, conditions=None, limit=None):
    """Returns the most used articles."""
    with connection as cursor:
      articles = cursor.Execute("""SELECT
          count(collectionArticle.article) as count,
          article.*
        FROM
          `collectionArticle`,
          `article`,
          `collection`
        WHERE
          collectionArticle.article = article.ID and
          collectionArticle.collection = collection.ID and
          article.%s and
          collection.%s
          %s
        GROUP BY
          collectionArticle.article
        ORDER BY
           count DESC
        %s""" %
           (NOTDELETED, NOTDELETED,
           'and %s' % ' and '.join(conditions) if conditions else '',
           ('LIMIT %d' % limit if limit else '')))
    for article in articles:
      yield cls(connection, article)

  def _Clean(self):
    if not self['name']:
      raise InvalidNameError('Provide a valid name')
    self['name'] = re.search('([\w\-_\.,]+)',
        self['name'].replace(' ', '_')).groups()[0][:255]
    if not self['name']:
      raise InvalidNameError('Provide a valid name')

  def Delete(self):
    """Overwrites the default Delete and sets the dateDeleted datetime instead"""
    self['dateDeleted'] = str(pytz.utc.localize(
        datetime.datetime.utcnow()))[0:19]
    self.Save()


class CollectionArticle(SanitizedRecord):
  """Abstraction for the CMS CollectionArticle model"""

  _PRIMARY_KEY = 'article', 'collection'

  @classmethod
  def FromCollectionAndArticle(cls, connection, collection, article):
    """Returns the Article of the given ID for a given collection.

    Arguments:
      @ connection: sqltalk.connection
        Database connection to use.
      @ collection: int
        The ID of the collection.
      @ article: int
        The ID of the article.

    Raises:
      NotExistError:
        The given article name does not exist.

    Returns:
      Article: article abstraction class.
    """
    with connection as cursor:
      article = cursor.Select(
          fields=('collectionArticle.*'),
          table=('article', 'collectionArticle', 'collection'),
          conditions=('article.ID=%d' % article,
                      'article.ID=collectionArticle.article',
                      'collectionArticle.collection=collection.ID',
                      'collection.ID=%d' % collection))
    if not article:
      raise cls.NotExistError(
          'There is no articleCollection with common name %s/%s' % (
              collection, safe_article))
    return cls(connection, article[0])

  @classmethod
  def FromCollectionAndUrl(cls, connection, collection, url):
    """Returns the Article of the given ID for a given collection.

    Arguments:
      @ connection: sqltalk.connection
        Database connection to use.
      @ collection: int
        The ID of the collection.
      @ url: str
        The url for the requested article.

    Raises:
      NotExistError:
        The give url does not exist.

    Returns:
      Article: article abstraction class.
    """
    safe_url = connection.EscapeValues(url)
    with connection as cursor:
      article = cursor.Select(
          fields=('collectionArticle.*'),
          table=('article', 'collectionArticle', 'collection'),
          conditions=('article.url=%s' % safe_url,
                      'article.ID=collectionArticle.article',
                      'collectionArticle.collection=collection.ID',
                      'collection.ID=%d' % collection))
    if not article:
      raise cls.NotExistError(
          'There is no articleCollection with url %d/%s' % (
              collection, url))
    return cls(connection, article[0])

  def _Clean(self):
    if not self['template']:
      raise InvalidNameError('Provide a valid template')
    self['template'] = re.search('([\w\-_\.,]+)',
        self['template'].replace(' ', '_')).groups()[0][:50]
    if not self['template']:
      raise InvalidNameError('Provide a valid template')
    if self['url']:
      self['url'] = re.search('([\w\-_\.,/ ]+)',
          self['url']).groups()[0][:50]
      if not self['url']:
        raise InvalidNameError('Provide a valid url')


class MenuArticle(SanitizedRecord):
  """Abstraction for the CMS MenuArticle model"""

  @classmethod
  def FromMenuArticle(cls, connection, menu, article):
    """Returns the Article of the given common name for a given menu.

    Arguments:
      @ connection: sqltalk.connection
        Database connection to use.
      @ menu: int
        The ID of the menu.
      @ article: int
        The ID of the article.

    Raises:
      NotExistError:
        The given article name does not exist.

    Returns:
      Article: article abstraction class.
    """
    with connection as cursor:
      menuArticle = cursor.Select(
          fields=('menuArticle.*'),
          table=('article', 'menuArticle', 'menu'),
          conditions=('article.ID=%d' % article,
                      'article.ID=menuArticle.article',
                      'menuArticle.menu=menu.ID',
                      'menu.ID=%d' % menu
                      ))
    if not menuArticle:
      raise cls.NotExistError(
          'There is no menuArticle with common name %d/%d' % (
              menu, article))
    return cls(connection, menuArticle[0])

  def _Clean(self):
    if self['name']:
      self['name'] = re.search('([\w\-_\.,/ ]+)',
          self['name']).groups()[0][:50]
      if not self['name']:
        raise InvalidNameError('Provide a valid name')


class Atom(model.Record):
  """Atom"""

  def AddToArticle(self, article):
    """Adds this atom to the given article."""
    sort = 0
    with self.connection as cursor:
      maxsort = cursor.Select(table='articleAtom',
          conditions='article = %d' % article,
          fields='max(sortorder) as max',
          escape=False)
      if maxsort[0]['max'] is not None:
        sort = maxsort[0]['max'] + 1
      cursor.Insert(table='articleAtom',
                    values={'article': article,
                            'atom': self.key,
                            'sortorder': sort})

  def RemoveFromArticle(self, article):
    """Removes this atom from the given article."""
    with self.connection as cursor:
      cursor.Delete(table='articleAtom',
                    conditions=('article=%d' % article,
                                'atom=%d' % self))

  def Articles(self):
    """Returns all Articles that use this atom"""
    with self.connection as cursor:
      articles = cursor.Select(
          fields=('article.*'),
          table=('articleAtom', 'article'),
          conditions=('articleAtom.atom=%d' % self,
                      'articleAtom.article=article.ID'))

    if not articles:
      raise self.NotExistError(
          'There are no articles for this atom')
    for article in articles:
      yield Article(self.connection, article)

  def Content(self):
    """Returns the content as a dict"""
    return json.loads(self['content'])

  def Render(self, parser):
    """Render the atom in its template"""
    atomfields = self.Content()
    schema = self['type'].Fields()
    typefields = schema['properties'] if 'properties' in schema else False
    replacements = {}
    atomfields = apply_markdown(atomfields, schema)

    if not typefields:
      replacements['root'] = atomfields
      return parser.ParseString(self['type']['template'], **replacements)

    for field in typefields:
      if field in atomfields.keys():
        replacements[field] = atomfields[field]
    return parser.ParseString(self['type']['template'], **replacements)

  def SetArticlePosition(self, article, position):
    """Sets the sortorder for this atom in the given article at the given position."""
    with self.connection as cursor:
      cursor.Execute("""update
                          articleAtom
                        set
                          sortorder = %d
                        where
                          atom=%d and
                          article=%d
                        """ % (max(0, position), self.key, int(article)))

  @classmethod
  def FromPrimaryAndClient(cls, connection, pkey_value, client):
    """Returns the atom requested if it belongs to a client owned article."""
    atoms = list(cls.List(connection,
        fields=('atom.*'),
        tables=('article', 'articleAtom', 'atom'),
        conditions=('atom.ID = %d' % pkey_value,
                    'article.client = %d' % client,
                    'article.ID = articleAtom.article',
                    'articleAtom.atom = %d' % pkey_value)))
    if atoms:
      return atoms[0]
    raise cls.NotExistError(
          'Unable to load atom %r' % pkey_value)


class Menu(SanitizedRecord):
  """Menu abstraction"""

  @classmethod
  def FromNameAndCollection(cls, connection, collection, menu):
    """Returns the Menu of the given common name for a given collection.

    Arguments:
      @ connection: sqltalk.connection
        Database connection to use.
      @ collection: int
        The  id of the collection.
      @ article: str
        The common name of the menu.

    Raises:
      NotExistError:
        The given menu name does not exist.

    Returns:
      Menu: menu abstraction class.
    """
    safe_menu = connection.EscapeValues(menu)
    with connection as cursor:
      menu = cursor.Select(
          table='menu',
          conditions=('menu.name=%s' % safe_menu,
                      'menu.collection=%d' % collection,
                      'menu.%s' % NOTDELETED))
    if not menu:
      raise cls.NotExistError(
          'There is no menu with name: %s in collection: %s' % (menu, collection))
    return cls(connection, menu[0])

  @classmethod
  def List(cls, *args, **kwargs):
    """Yields a Record object for every table entry."""
    kwargs['conditions'] = [NOTDELETED] + kwargs['conditions']
    return super().List(*args, **kwargs)

  @classmethod
  def Search(cls, connection, conditions=None, query=None):
    """Returns the articles matching the search

      Arguments:
      @ connection: sqltalk.connection
        Database connection to use.
      % query: str
        Filters on name
    """
    return cls.List(
      connection,
      conditions=['name like "%%%s%%"' % connection.EscapeValues(query)[1:-1]] + (conditions or []),
      order=[('menu.dateCreated', True)])

  def Articles(self, conditions=None):
    """Yields all the articles for this menu."""
    with self.connection as cursor:
      articles = cursor.Select(
          table=('menuArticle', 'article', 'collectionArticle', 'menu'),
          fields=('menuArticle.sortorder',
                  ('menuArticle.name', 'menuname'), 'article.name',
                  'article.ID', 'collectionArticle.url'),
          conditions=['menuArticle.menu=%d' % self['ID'],
                      'menuArticle.menu = menu.ID',
                      'menuArticle.article=article.ID',
                      'collectionArticle.article = article.ID',
                      'collectionArticle.collection = menu.collection',
                      'article.%s' % NOTDELETED] + (conditions or []),
          order=[['menuArticle.sortorder', False]])
    if not articles:
      raise self.NotExistError('There are no articles for this menu')
    for article in articles:
      yield Article(self.connection, article)

  def AddArticles(self, articles):
    """Adds the given list of article IDs to this menu."""
    # filter out non numeric input
    try:
      articles = list(map(int, articles))
    except ValueError:
      return False  # This prevents SQL injection.
    # filter out non existant articles
    articles = list(Article.List(self.connection,
        fields=Article._PRIMARY_KEY,
        conditions=('%s in (%s)' % (Article._PRIMARY_KEY, ','.join(map(str, articles))),
                    'client = %d' % self['client']), distinct=True))
    # what remains is a unique set of existing articles, which we can add
    articles = set([article['ID'] for article in articles])
    if not articles:
      return False
    with self.connection as cursor:
      maxsort = cursor.Select(table='menuArticle',
                              conditions='menu=%d' % self,
                              fields='max(sortorder) as max',
                              escape=False)
      sort = 0
      if maxsort and maxsort[0]['max'] is not None:
        sort = maxsort[0]['max'] + 1

      for article in articles:
        try:
          cursor.Insert(table='menuArticle',
                        values={'menu': self.key,
                                'article': article,
                                'sortorder': sort})
          sort += 1
        except self.connection.IntegrityError:
          # was aleady present for this menu
          pass
    return True

  def _Clean(self):
    if not self['name']:
      raise InvalidNameError('Provide a valid name')
    self['name'] = re.search('([\w\-_\.,]+)',
        self['name'].replace(' ', '_')).groups()[0][:50]
    if not self['name']:
      raise InvalidNameError('Provide a valid name')

  def Delete(self):
    """Overwrites the default Delete and sets the dateDeleted datetime instead"""
    self['dateDeleted'] = str(pytz.utc.localize(
        datetime.datetime.utcnow()))[0:19]
    self.Save()


class Client(SanitizedRecord):
  """Global client model"""

  def CollectionSearch(self, query):
    """Searches the collection table for this client."""
    return Collection.Search(self.connection,
        conditions=['client=%d' % self], query=query)

  def Collections(self):
    """Get all collections owned by this client."""
    return Collection.ReverseList(self.connection,
        conditions=['client=%d' % self])

  def CollectionFromName(self, name):
    """Get a collection by name for this client."""
    return Collection.FromName(self.connection,
        name=name,
        conditions=['client=%d' % self])

  def Menus(self, limit=None):
    """Get all menus owned by this client."""
    return Menu.List(self.connection,
        conditions=[NOTDELETED, 'client=%d' % self],
        limit=limit)

  def MenuSearch(self, query):
    """Searches the menu table for this client."""
    return Menu.Search(self.connection,
        conditions=['client=%d' % self], query=query)

  def MenuFromName(self, collection, name):
    """Get a menu by name for this client."""
    collection = self.CollectionFromName(collection)
    return collection.Menu(name)

  def Articles(self, order=None, limit=None):
    """Get all articles owned by this client."""
    return Article.List(self.connection,
        conditions=[NOTDELETED, 'client=%d' % self],
        order=order,
        limit=limit)

  def TopArticles(self, limit=None):
    """Get the best articles owned by this client."""
    return Article.TopArticles(self.connection,
        conditions=['article.%s' % NOTDELETED, 'article.client=%d' % self],
        limit=limit)

  def ArticleSearch(self, query):
    """Searches the article table for the client."""
    return Article.Search(self.connection,
        conditions=['client=%d' % self],
        query=query)

  def ArticleFromName(self, name):
    """Get an article by name for this client."""
    return Article.FromName(self.connection,
        name=name,
        conditions=['client=%d' % self])

  def Article(self, pkey_value):
    """Get an article by primary key for this client."""
    return Article.FromPrimaryAndClient(self.connection, pkey_value, self['ID'])

  def TypeArticles(self, typeId, conditions=None, query=None):
    """Yields all the articles for the given type."""
    return Article.FromClientAndType(self.connection, typeId,
          self['ID'], conditions=conditions, query=query)

  def Variable(self, pkey_value):
    """Get a variable by primary key for this client."""
    return Variable.FromPrimaryAndClient(self.connection, pkey_value, self['ID'])

  def Type(self, pkey_value):
    """Get a type by primary key for this client."""
    return Type.FromPrimaryAndClient(self.connection, pkey_value, self['ID'])

  def Variables(self):
    """Get all variables owned by this client."""
    return Variable.List(self.connection,
        conditions=['client=%d' % self])

  def VariablesFromTag(self, tag):
    """Get a variable by tag for this client."""
    return Variable.FromTag(self.connection,
        tag=tag,
        conditions=['client=%d' % self])

  def Types(self):
    """Get all types owned by this client or base types."""
    return Type.List(self.connection,
        conditions=['(client=%d or client is null)' % self],
        order=[('client', True)])

  def Apiusers(self):
    """Get all apiusers owned by this client."""
    return Apiuser.List(self.connection, conditions=['(client=%d)' % self])

  def Users(self):
    """Get all users for this client."""
    return User.List(self.connection, conditions=['(client=%d)' % self])

  def TypeSearch(self, query):
    """Searches the type table for the client."""
    return Type.Search(self.connection,
        conditions=['(client=%d or client is null)' % self],
        order=[('client', True)],
        query=query)

  def TypeFromName(self, name):
    """Get a type by name for this client."""
    return Type.FromName(self.connection,
        name=name,
        conditions=['(client=%d or client is null)' % self],
        order=[('client', True)])

  def Atom(self, pkey_value):
    """Get an atom by pkey_value for this client."""
    return Atom.FromPrimaryAndClient(self.connection, pkey_value, self['ID'])

  def _Clean(self):
    if not self['name']:
      raise InvalidNameError('Provide a valid name')
    self['name'] = re.search('([\w\-_\.,]+)',
        self['name'].replace(' ', '_')).groups()[0][:45]
    if not self['name']:
      raise InvalidNameError('Provide a valid name')
    self['active'] = 'true' if self['active'] == 'true' else 'false'


class Type(SanitizedRecord):
  """Global atom types"""

  def _Clean():
    if not self['name']:
      raise InvalidNameError('Provide a valid name')
    self['name'] = re.search('([\w\-_\.,]+)',
        self['name'].replace(' ', '_')).groups()[0][:45]
    if not self['name']:
      raise InvalidNameError('Provide a valid name')

  def Delete(self):
    """Overwrites the default Delete and sets the dateDeleted datetime instead"""
    self['dateDeleted'] = str(pytz.utc.localize(
        datetime.datetime.utcnow()))[0:19]
    self.Save()

  def Fields(self):
    """Returns the schema's fields as a dict"""
    return json.loads(self['schema'])

  @classmethod
  def List(cls, connection, conditions=None, order=None):
    """Yields a Record object for every table entry."""
    with connection as cursor:
      records = cursor.Select(table=cls.TableName(),
                              conditions=[NOTDELETED] + (conditions or []),
                              order=order)
    for record in records:
      yield cls(connection, record)

  @classmethod
  def Search(cls, connection, conditions=None, query=None, order=None):
    """Returns the types matching the search

      Arguments:
      @ connection: sqltalk.connection
        Database connection to use.
      % query: str
        Filters on name
    """
    return cls.List(
      connection,
      conditions=['name like "%%%s%%"' % connection.EscapeValues(query)[1:-1]] + (conditions or []),
      order=order)

  @classmethod
  def FromName(cls, connection, name, conditions=None, order=None):
    """Returns the type of the given common name.

    Arguments:
      @ connection: sqltalk.connection
        Database connection to use.
      @ name: str
        The common name of the type.

    Raises:
      NotExistError:
        The given type name does not exist.

    Returns:
      TYpe: type abstraction class.
    """
    safe_name = connection.EscapeValues(name)
    with connection as cursor:
      typedetails = cursor.Select(table=cls.TableName(),
                                  conditions=['name=%s' % safe_name,
                                              NOTDELETED] + (conditions or []),
                                  order=order,
                                  limit=1)
    if not typedetails:
      raise cls.NotExistError(
          'There is no type with common name %r' % name)
    return cls(connection, typedetails[0])

  @classmethod
  def FromPrimaryAndClient(cls, connection, pkey_value, client):
    """Returns the type requested if it belongs to a client."""
    atomtype = list(cls.List(connection,
        conditions=['ID = %d' % int(pkey_value),
                    '(client=%d or client is null)' % client]))
    if atomtype:
      return atomtype[0]
    raise cls.NotExistError('Unable to load type %r' % pkey_value)


class Variable(SanitizedRecord):
  """Global replace vars"""

  def _Clean(self):
    # strip brackets if user didn't understand.
    if self['tag'].startswith('['):
      self['tag'] = self['tag'][1:]
    if self['tag'].endswith(']'):
      self['tag'] = self['tag'][:-1]
    # clean up other chars.
    self['tag'] = re.search('([\w\-_\.,]+)',
        self['tag'].replace(' ', '_')).groups()[0][:100]
    if 'value' in self:
      self['value'] = self['value'][:255]
    if not self['tag']:
      raise InvalidNameError('Provide a valid name')

  @classmethod
  def FromPrimaryAndClient(cls, connection, pkey_value, client):
    """Returns the variable requested if it belongs to a client."""
    variable = list(cls.List(connection,
        conditions=['ID = %d' % int(pkey_value),
                    '(client=%d or client is null)' % client]))
    if variable:
      return variable[0]
    raise cls.NotExistError('Unable to load variable %r' % pkey_value)

  @classmethod
  def FromTag(cls, connection, tag, conditions=None):
    """Returns the variable requested by tag."""
    safe_tag = connection.EscapeValues(tag)
    conditions = [] if conditions is None else conditions
    conditions.append('tag = %s' % safe_tag)

    variable = list(cls.List(connection, conditions=conditions))
    if variable:
      return variable[0]
    raise cls.NotExistError('Unable to load variable %r' % tag)


class User(SanitizedRecord):
  """Provides interaction to the user table"""

  @classmethod
  def FromEmail(cls, connection, email, conditions=None):
    """Returns the user with the given email address.

    Arguments:
      @ connection: sqltalk.connection
        Database connection to use.
      @ email: str
        The email address of the user.

    Raises:
      NotExistError:
        The given user does not exist.

    Returns:
      User: user abstraction class.
    """
    with connection as cursor:
      user = cursor.Select(table=cls.TableName(),
          conditions=['email=%s' % connection.EscapeValues(email),
                      'active = "true"'] + (conditions or []))
    if not user:
      raise cls.NotExistError(
          'There is no user with the email address: %r' % email)
    return cls(connection, user[0])

  @classmethod
  def FromLogin(cls, connection, email, password):
    """Returns the user with the given login details."""
    user = list(cls.List(connection,
        conditions=('email = %s' % connection.EscapeValues(email),
                    'active = "true"')))
    if not user:
      # fake a login attempt, and slow down, even though we know its never going
      # to end in a valid login, we dont want to let anyone know the account
      # does or does not exist.
      if connection.debug:
        print('password for non existant user would have been: ', pbkdf2_sha256.hash(password))
      raise cls.NotExistError('Invalid login, or inactive account.')
    if pbkdf2_sha256.verify(password, user[0]['password']):
      if user[0]['client']['active'] != 'true':
        raise ValueError('Client not active, session invalid')
      return user[0]
    raise cls.NotExistError('Invalid password')

  def UpdatePassword(self, password):
    """Hashes the password and stores it in the database"""
    if len(password) < 8:
      raise ValueError('password too short, 8 characters minimal.')
    self['password'] = pbkdf2_sha256.hash(password)
    self.Save()

  def _Clean(self):
    self['email'] = self['email'][:255]
    self['active'] = 'true' if self['active'] == 'true' else 'false'

  def PasswordResetHash(self):
    """Returns a hash based on the user's ID, name and password."""
    return pbkdf2_sha256.hash('%d%s%s' % (
         self['ID'], self['email'], self['password']),
         salt=bytes(self['ID']))


class Session(model.SecureCookie):
  """Provides a model to request the secure cookie named 'session'"""


class Apiuser(SanitizedRecord):
  """Provides a model abstraction for the apiuser table"""

  KEYLENGTH = 32

  def _Clean(self):
    if 'collectionfilter' in self and self['collectionfilter']:
      self['collectionfilter'] = self['collectionfilter'][:255]
    self['name'] = re.search('([\w\-_\.,]+)',
        self['name'].replace(' ', '_')).groups()[0][:45]
    if not self['name']:
      raise InvalidNameError('Provide a valid name')

  def _PreCreate(self, cursor):
    self['key'] = secrets.token_hex(int(self.KEYLENGTH/2))
    if 'active' not in self:
      self['active'] = 'true'
    super()._PreCreate(cursor)

  @classmethod
  def FromKey(cls, connection, key):
    """Returns a user object by API key."""
    if not key:
      raise cls.NotExistError('No API key given.')
    user = list(cls.List(connection,
        conditions=('`key` = %s' % connection.EscapeValues(key),
                    '`active` = "true"')))
    if not user:
      raise cls.NotExistError('Invalid key, or inactive key.')
    if user[0]['client']['active'] == "true":
      return user[0]
    raise cls.NotExistError('Inactive client account.')


def apply_markdown(atom, schema):
  """Helper function to walk over a dict tree, and see if markdown is eabled by
  simultaniously walking the schema dict, any markdown fields will be subjected
  to Markdown parsing

  Returns the original dict, with any markdown rendering done in place.
  """
  if isinstance(atom, dict):
      schema = schema['properties']
      ratom = {}
      for key, value in atom.items():
        if isinstance(value, dict):
          ratom[key] = apply_markdown(value, schema.get(key, {}))
        elif isinstance(value, list) or isinstance(value, tuple):
          ratom[key] = [apply_markdown(v, schema.get(key, {}).get('items', {})) for v in value]
        else:
          ratom[key] = HTMLsafestring(markdown.convert(HTMLsafestring(value, unsafe=True))) if 'markdown' in schema.get(key, {}) and schema[key]['markdown'] else value
      return ratom
  elif isinstance(atom, list) or isinstance(atom, tuple):
    atom = [apply_markdown(item, schema.get('items', {})) for item in atom]
  elif 'markdown' in schema and schema['markdown']:
    atom = HTMLsafestring(markdown.convert(HTMLsafestring(atom, unsafe=True)))
  return atom


class InvalidNameError(Exception):
  """Invalid name value."""


NotExistError = model.NotExistError
