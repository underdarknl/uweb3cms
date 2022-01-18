#!/usr/bin/python3
"""Request handlers for the uWeb3 CMS"""

# standard modules
import time
import json
import base64
import binascii

# custom modules
import uweb3
from uweb3 import templateparser
from . import model
from uweb3.libs import mail

def Prettyjson(inputstring, indent=2):
  """Takes a json string, tries to parse it, and outputs it as a string, but now
  made prettier, and more human readable.

  Optionally the indent level van be set, it defaults to 2 spaces."""
  try:
    return json.dumps(json.loads(inputstring), indent=indent)
  except json.JSONDecodeError as error:
    return inputstring

def apiuser(f):
  """Decorator to check if the given API key is allowed to access the resource."""
  def wrapper(*args, **kwargs):
    # This is bypassed if a user is already logged in trough a session
    self = args[0]
    if self.user:
      self.apikey = None
      self.client = self.user['client']
      return f(*args, **kwargs)
    key = None
    if 'apikey' in self.get:
      key = self.get.getfirst('apikey')
    elif 'apikey' in self.post:
      key = self.post.getfirst('apikey')
    elif 'apikey' in self.req.headers:
      key = self.req.headers.get('apikey')
    try:
      self.apikey = model.Apiuser.FromKey(self.connection, key)
    except model.Apiuser.NotExistError as apierror:
      return uweb3.Response(content={'error': str(apierror)}, httpcode=403)
    self.client = self.apikey['client']
    return f(*args, **kwargs)
  return wrapper

def NotExistsErrorCatcher(f):
  """Decorator to return a 404 if a NotExistError exception was returned."""
  def wrapper(*args, **kwargs):
    try:
      return f(*args, **kwargs)
    except model.NotExistError as error:
      return args[0].RequestInvalidcommand(error=error)
  return wrapper


class AtomHandler(dict):
  """Wrapper that allows dynamic lookups for atoms from the database.

  Designed to be used by the templater parser.
  """

  def __init__(self, pagemaker, parser):
    """Initializes an atom handler object."""
    self.pagemaker = pagemaker
    self.parser = parser
    self.atoms = {}

  def __getitem__(self, atom):
    """Returns a rendered atom.

    Used for the templateparser [atom:ID] replacement.
    """
    atom = int(atom)
    if atom not in self.atoms:
      client = self.pagemaker.user['client'] if self.pagemaker.user else self.pagemaker.apikey['client']
      try:
        self.atoms[atom] = model.Atom.FromPrimaryAndClient(
            self.pagemaker.connection,
            atom,
            client
            ).Render(self.parser)
      except (model.Atom.NotExistError, ValueError):
        return '[Unknown atom]'
    return self.atoms[atom]


class PageMaker(uweb3.DebuggingPageMaker, uweb3.LoginMixin):
  """Holds all the request handlers for the application"""

  def _PostInit(self):
    """Sets up all the default vars"""
    self.parser.RegisterFunction('ToID', lambda x: x.replace(' ', ''))
    self.parser.RegisterFunction('DateOnly', lambda x: str(x)[0:10])
    self.parser.RegisterFunction('TextareaRowCount', lambda x: len(str(x).split('\n')))
    self.parser.RegisterFunction('prettyjson', Prettyjson)
    self.parser.RegisterTag('header', self.parser.JITTag(lambda: self.parser.Parse(
                'parts/header.html')))
    self.parser.RegisterTag('footer', self.parser.JITTag(lambda: self.parser.Parse(
                'parts/footer.html', year=time.strftime('%Y'))))

    self.parser.RegisterFunction('NullString', lambda x: '' if x is None else x)
    self.validatexsrf()
    self.parser.RegisterTag('xsrf', self._Get_XSRF())
    self._replacevariables = None
    self.parser.RegisterTag('user', self.user)

    # set up a sepereate parser to not have the other vars available inside the rendered atoms
    self.safeparser = templateparser.Parser()
    self.atomhandler = AtomHandler(self, self.safeparser)
    self.parser.RegisterTag('atom', self.atomhandler)
    self.safeparser.RegisterTag('atom', self.atomhandler)

    self.config.Read()

  @uweb3.decorators.TemplateParser('login.html')
  def RequestLogin(self, url=None):
    """Please login"""
    if self.user:
      return self.RequestIndex()
    if not url and 'url' in self.get:
      url = self.get.getfirst('url')
    return {'url': url}

  @uweb3.decorators.checkxsrf
  @uweb3.decorators.TemplateParser('logout.html')
  def RequestLogout(self):
    """Handles logouts"""
    message = 'You were already logged out.'
    if self.user:
      message = ''
      if 'action' in self.post:
        session = model.Session(self.connection)
        session.Delete()
        message = 'Logged out.'
    return {'message': message}

  @uweb3.decorators.checkxsrf
  def HandleLogin(self):
    """Handles a username/password combo post."""
    if (self.user or
        'email' not in self.post or
        'password' not in self.post):
      return self.RequestIndex()
    url = self.post.getfirst('url', None) if self.post.getfirst('url', '').startswith('/') else '/'
    try:
      self._user = model.User.FromLogin(self.connection,
          self.post.getfirst('email'), self.post.getfirst('password'))
      model.Session.Create(self.connection, int(self.user), path="/")
      self.client = self._user['client']
      print('login successful.', self.post.getfirst('email'))
      # redirect 303 to make sure we GET the next page, not post again to avoid leaking login details.
      return self.req.Redirect(url, httpcode=303)
    except model.User.NotExistError as error:
      self.parser.RegisterTag('loginerror', '%s' % error)
      print('login failed.', self.post.getfirst('email'))
    except ValueError as error:
      self.parser.RegisterTag('loginerror', '%s' % error)
      print('login failed, client inctive.', self.post.getfirst('email'))
    return self.RequestLogin(url)

  @uweb3.decorators.checkxsrf
  def RequestResetPassword(self, email=None, resethash=None):
    """Handles the post for the reset password."""
    message = None
    error = False

    if not email and not resethash and not self.post:
      return self.parser.Parse('reset.html', message='Sorry, something is wrong, maybe you reloaded this page by accident? please try again by asking for a new reset password.')
    if not email and not resethash:
      try:
        user = model.User.FromEmail(self.connection,
                                    self.post.getfirst('email', ''))
      except model.User.NotExistError:
        error = True
      if not error:
        resethash = user.PasswordResetHash()
        content = self.parser.Parse('email/resetpass.txt', email=user['email'],
                                    host=self.options['general']['host'],
                                    resethash=resethash)
        try:
          with mail.MailSender(local_hostname=self.options['general']['host']) as send_mail:
            send_mail.Text(user['email'], 'CMS password reset', content)
        except mail.SMTPConnectError:
          if not self.debug:
            return self.Error('Mail could not be send due to server error, please contact support.')
        if self.debug:
          print('Password reset for %s:' % user['email'], content)
      message = 'If that was an email address that we know, a mail with reset instructions will be in your mailbox soon.'
      return self.parser.Parse('reset.html', message=message)
    try:
      user = model.User.FromEmail(self.connection, email)
    except model.User.NotExistError:
      return self.parser.Parse('reset.html', message='Sorry, that\'s not the right reset code.')
    if resethash != user.PasswordResetHash():
      return self.parser.Parse('reset.html', message='Sorry, that\'s not the right reset code.')

    if 'password' in self.post:
      if self.post.getfirst('password') == self.post.getfirst('password_confirm', ''):
        try:
          user.UpdatePassword(self.post.getfirst('password'))
        except ValueError:
          return self.parser.Parse('reset.html', message='Password too short, 8 characters minimal.')
        model.Session.Create(self.connection, int(user), path="/")
        self._user = user
        self.client = self._user['client']
        return self.parser.Parse('reset.html', message='Your password has been updated, and you are logged in.')
      else:
        return self.parser.Parse('reset.html', message='The passwords don\'t match.')
    return self.parser.Parse('resetform.html',
                             resethash=resethash,
                             resetuser=user,
                             message='')

  def _ReadSession(self):
    """Attempts to read the session for this user from his session cookie"""
    try:
      user = model.Session(self.connection)
    except Exception:
      raise ValueError('Session cookie invalid')
    user = model.User.FromPrimary(self.connection, int(str(user)))
    if user['active'] != 'true':
      raise ValueError('User not active, session invalid')
    if user['client']['active'] != 'true':
      raise ValueError('Client not active, session invalid')
    self.client = user['client']
    return user

  @uweb3.decorators.checkxsrf
  @uweb3.decorators.TemplateParser('setup.html')
  def RequestSetup(self):
    """Allows the user to setup various fields, and create an admin user.

    If these fields are already filled out, this page will not function any
    longer.
    """
    if self.options.get('general', {}).get('host', False):
      return self.RequestIndex()
    if (self.post and
        'email' in self.post and
        'password' in self.post and
        'password_confirm' in self.post and
        'hostname' in self.post and
        self.post.getfirst('password') == self.post.getfirst('password_confirm')):
      user = model.User.Create(self.connection,
          {'client': 0,
           'email': self.post.getfirst('email'),
           'password': '',
           'active': 'true'})
      try:
        user.UpdatePassword(self.post.getfirst('password', ''))
      except ValueError:
        return {'error': 'Password too short, 8 characters minimal.'}
      self.config.Create('general', 'host', self.post.getfirst('hostname'))
      model.Session.Create(self.connection, int(user), path="/")
      return self.req.Redirect('/', httpcode=301)
    if self.post:
      return {'error': 'Not all fields are properly filled out.'}
    return

  @uweb3.decorators.loggedin
  @uweb3.decorators.checkxsrf
  @uweb3.decorators.TemplateParser('admin.html')
  def RequestAdmin(self):
    """Returns the admin page."""
    if self.client['ID'] != 0 and not self.user['clientadmin']:
      return self.req.Redirect('/')

    postfields = ['useremail', 'userclient', 'useractive', 'userpassword',
                  'userpassword_confirm', 'userdelete',
                  'userapiaccess', 'usertypeaccess', 'userclientadmin']
    if self.client['ID'] == 0:
      currentclients = list(model.Client.List(self.connection))
      currentusers = list(model.User.List(self.connection))
      postfields += ['clientname', 'clientactive', 'clientdelete']
    else:
      currentclients = None
      currentusers = list(self.client.Users())
      clients = None

    if self.post:
      values = {}
      for key in postfields:
        values[key] = self.post.getfirst(key, {})
    if self.client['ID'] == 0:
      clients = []
      for client in currentclients:
        # client changes
        clientid = str(client['ID'])
        if ('clientname' in self.post and
            'new' not in values['clientname'] and
            client['ID'] != 0 and
            client['ID'] != self.client['ID']):
          if clientid in values['clientdelete']:
            client.Delete()
          else:
            if clientid in values['clientname']:
              client['name'] = values['clientname'][clientid]
            client['active'] = 'true' if clientid in values['clientactive'] else 'false'
            client.Save()
            clients.append(client)
        else:
          clients.append(client)

      # handle Client creation
      if ('clientname' in self.post and
          'new' in self.post.getfirst('clientname')):
        try:
          newclient = model.Client.Create(self.connection,
            {'name': self.post.getfirst('clientname').get('new', '').strip(),
             'active': self.post.getfirst('clientactive').get('new', 'true')})
          clients.append(newclient)
        except model.InvalidNameError:
          return {'clients': clients,
                  'clienterror': 'Provide a valid name for the new client.',
                  'users': currentusers}
        except self.connection.IntegrityError:
          return {'clients': clients,
                  'clienterror': 'That name was already used for another client.',
                  'users': currentusers}
        return {'clients': clients,
                'clientsucces': 'Your new client was added',
                'users': currentusers}

    users = []
    for user in currentusers:
      # user changes
      userid = str(user['ID'])

      # we are posting the edit form, not the new form
      if ('useremail' in self.post and
          'new' not in values['useremail']):
        if userid in values['userdelete']:
          if user['ID'] != 1 or user['ID'] == self.user['ID']:
            user.Delete()
        else:
          if userid in values['useremail']:
            user['email'] = values['useremail'][userid].strip()
          if self.client['ID'] == 0:
            try:
              if userid in values['userclient']:
                user['client'] = int(values['userclient'][userid])
            except ValueError:
              return {'clients': clients,
                      'usererror': 'Provide a valid client number.',
                      'users': currentusers}
          else:
            user['client'] = self.client['ID']

          if user['ID'] != 1 and user['ID'] != self.user['ID']:
            user['active'] = 'true' if userid in values['useractive'] else 'false'
          else:
            user['active'] = 'true'
          # handle password change
          if (userid in values['userpassword'] and
              userid in values['userpassword_confirm'] and
              len(values['userpassword'][userid].strip()) > 7):
            if values['userpassword'][userid].strip() != values['userpassword_confirm'][userid].strip():
              return {'clients': clients,
                      'usererror': 'Passwords do not match.',
                      'users': currentusers}
            try:
              user.UpdatePassword(values['userpassword'][userid].strip())
            except ValueError:
              return {'clients': clients,
                      'usererror': 'Password too short, 8 characters minimal.',
                      'users': currentusers}
            else:
              content = self.parser.Parse('email/updateuser.txt',
                email=user['email'],
                host=self.options['general']['host'],
                newpassword=values['userpassword'][userid].strip())
              try:
                with mail.MailSender(local_hostname=self.options['general']['host']) as send_mail:
                  send_mail.Text(self.user['email'], 'CMS account change', content)
              except mail.SMTPConnectError:
                if not self.debug:
                  return self.Error('Mail could not be send due to server error, please contact support.')
          user['apiaccess'] = 'true' if userid in values['userapiaccess'] else 'false'
          user['typeaccess'] = 'true' if userid in values['usertypeaccess'] else 'false'
          user['clientadmin'] = 'true' if userid in values['userclientadmin'] else 'false'
          user.Save()
          users.append(user)
      else:
        users.append(user)

    # handle User creation
    if ('useremail' in self.post and
        'new' in values['useremail']):
      try:
        newuser = model.User.Create(self.connection,
          {'email': values['useremail'].get('new', '').strip(),
           'active': values['useractive'].get('new', 'true'),
           'password': '',
           'client': int(values['userclient'].get('new', '')) if self.client['ID'] == 0 else self.client['ID'],
           'typeaccess': self.post.getfirst('userapiaccess', {}).get('new', 'false'),
           'apiaccess': self.post.getfirst('usertypeaccess', {}).get('new', 'false'),
           'clientadmin': self.post.getfirst('userclientadmin', {}).get('new', 'false')})
        try:
          newpassword = values['userpassword'].get('new', '').strip()
          newuser.UpdatePassword(newpassword)
        except ValueError:
          return {'clients': clients,
                  'usererror': 'Password too short, 8 characters minimal.',
                  'users': users}
        users.append(newuser)
      except model.InvalidNameError:
        return {'clients': clients,
                'usererror': 'Provide a valid email address for the new user.',
                'users': users}
      except ValueError:
        return {'clients': clients,
                'usererror': 'Provide a valid client ID for the new user.',
                'users': users}
      except self.connection.IntegrityError:
        return {'clients': clients,
                'usererror': 'That email address was already used for another user.',
                'users': users}
      else:
        content = self.parser.Parse('email/newuser.txt', email=newuser['email'],
                                    host=self.options['general']['host'],
                                    password=newpassword)
        try:
          with mail.MailSender(local_hostname=self.options['general']['host']) as send_mail:
            send_mail.Text(newuser['email'], 'CMS account', content)
        except mail.SMTPConnectError:
          if not self.debug:
            return self.Error('Mail could not be send due to server error, please contact support.')
      return {'clients': clients,
              'usersucces': 'Your new user was added',
              'users': users}
    return {'clients': clients,
            'users': users}

  @uweb3.decorators.loggedin
  def RequestIndex(self):
    """Returns the homepage"""
    return self.Collections()

  @uweb3.decorators.loggedin
  @uweb3.decorators.TemplateParser('collections.html')
  def Collections(self):
    """Returns the collections page"""
    collections = None
    query = ''
    if 'query' in self.post and self.post.getfirst('query', False):
      query = self.post.getfirst('query', '')
      collections = list(self.client.CollectionSearch(
          self.post.getfirst('query')))
    else:
      collections = self.client.Collections()
    return {
        'collections': list(collections),
        'query': query}

  @uweb3.decorators.loggedin
  @uweb3.decorators.TemplateParser('variables.html')
  def RequestVariables(self):
    """Returns the variables page"""
    return {'variables': self.client.Variables()}

  @uweb3.decorators.loggedin
  @uweb3.decorators.TemplateParser('types.html')
  def RequestTypes(self, message=None):
    """Returns the types page"""
    if not self.user['typeaccess']:
      return self.req.Redirect('/')
    query = ''
    if 'query' in self.get and self.get.getfirst('query', False):
      query = self.get.getfirst('query', '')
      types = list(self.client.TypeSearch(query))
    else:
      types = self.client.Types()
    return {'types': types,
            'query': query}

  @uweb3.decorators.loggedin
  @NotExistsErrorCatcher
  @uweb3.decorators.TemplateParser('type.html')
  def RequestType(self, name):
    """Returns the type page"""
    if not self.user['typeaccess']:
      return self.req.Redirect('/')
    return {'type': self.client.TypeFromName(name)}

  @uweb3.decorators.loggedin
  @NotExistsErrorCatcher
  @uweb3.decorators.checkxsrf
  def RequestTypeSave(self, name):
    """Update a Type, or forking it based on the owner."""
    if not self.user['typeaccess']:
      return self.req.Redirect('/')
    basetype = self.client.TypeFromName(name)
    basetype['name'] = self.post.getfirst('name', '')
    basetype['schema'] = self.post.getfirst('schema', '')
    basetype['template'] = self.post.getfirst('template', '')

    if not basetype['client'] and self.client['ID'] != 0:
      newtype = dict(basetype)
      if basetype['name'] == name:
        newtype['name'] = 'my_'+newtype['name']
      newtype['client'] = int(self.client)
      del(newtype['ID'])
      model.Type.Create(self.connection, newtype)
    else:
      basetype.Save()
    return self.RequestTypes('Type "%s" added' % basetype['name'])

  @uweb3.decorators.loggedin
  @uweb3.decorators.checkxsrf
  def RequestTypeNew(self):
    """Update a Type, or forking it based on the owner."""
    if not self.user['typeaccess']:
      return self.req.Redirect('/')
    try:
      newtype = model.Type.Create(self.connection,
        {'name': self.post.getfirst('name', ''),
         'schema':  self.post.getfirst('schema', ''),
         'template': self.post.getfirst('template', ''),
         'client': int(self.client)})
      return self.RequestTypes('Type "%s" added' % newtype['name'])
    except model.InvalidNameError:
      return self.RequestInvalidcommand(
                                error='Please enter a valid name for the type.')
    except self.connection.IntegrityError:
      return self.Error('That name was already taken, go back, try again!', 200)

  @uweb3.decorators.loggedin
  @NotExistsErrorCatcher
  @uweb3.decorators.checkxsrf
  def RequestTypeRemove(self, name):
    """Removes the type"""
    removeabletype = self.client.TypeFromName(name)
    if removeabletype['client'] and removeabletype['client']['ID'] != 0:
      removeabletype.Delete()
      return self.RequestTypes('Type removed.')
    return self.RequestTypes('Type not removed. Base types cannot be removed.')

  @uweb3.decorators.loggedin
  @uweb3.decorators.TemplateParser('typearticles.html')
  def RequestTypeArticles(self, name):
    """Returns the type's list of articles who use it."""
    typedetails = self.client.TypeFromName(name)
    query = self.get.getfirst('query', None)
    try:
      articles = list(self.client.TypeArticles(typedetails.key,
         query=query))
    except model.NotExistError:
      articles = []
    return {'type': typedetails,
            'articles': articles,
            'query': query}

  @uweb3.decorators.loggedin
  @uweb3.decorators.checkxsrf
  def RequestCollectionNew(self):
    """Requests the creation of a new collection."""
    try:
      collection = model.Collection.Create(self.connection,
          {'name': self.post.getfirst('name', '').replace(' ', '_'),
           'client': int(self.client)})
    except model.InvalidNameError:
      return self.RequestInvalidcommand(
                          error='Please enter a valid name for the collection.')
    except self.connection.IntegrityError:
      return self.Error('That name was already taken, go back, try again!', 200)

    base = self.post.getfirst('base', None)
    if base:
      try:
        basecollection = self.client.CollectionFromName(base)
      except model.Collection.NotExistError:
        return self.req.Redirect('/collection/%s' % collection['name'], httpcode=301)

      articles = basecollection.Articles()
      articlelist = []
      try:
        for article in articles:
          articlelist.append(article['ID'])
        collection.AddArticles(articlelist)
      except model.Collection.NotExistError:
        pass
    return self.req.Redirect('/collection/%s' % collection['name'], httpcode=301)

  @uweb3.decorators.loggedin
  @NotExistsErrorCatcher
  @uweb3.decorators.checkxsrf
  def RequestCollectionRemove(self, collection):
    """Removes the requested collection"""
    collection = self.client.CollectionFromName(collection)
    collection.Delete()
    return self.req.Redirect('/', httpcode=301)

  @uweb3.decorators.loggedin
  @NotExistsErrorCatcher
  @uweb3.decorators.TemplateParser('collection.html')
  def RequestCollection(self, collection, message=None):
    """Returns a collection"""
    collection = self.client.CollectionFromName(collection)
    articles = None
    try:
      articles = list(collection.Articles())
      articlelist = []
      for article in articles:
        articlelist.append(article['ID'])
    except model.Collection.NotExistError:
      pass

    toparticles = None
    allarticles = None
    query = self.get.getfirst('query', None)
    try:
      if query:
        allarticles = list(self.client.ArticleSearch(query))
      else:
        allarticles = list(self.client.Articles(order=[('ID', True)], limit=20))
        toparticles = list(self.client.TopArticles(limit=20))
    except model.Collection.NotExistError:
      pass

    newarticles = []
    if allarticles:
      if not articles:
        newarticles = allarticles
      else:
        for article in allarticles:
          if article['ID'] not in articlelist:
            newarticles.append(article)
    return {'collection': collection,
            'articles': articles or '',
            'toparticles': toparticles or '',
            'allarticles': newarticles or '',
            'query': query,
            'message': message,
            'menus': list(collection.Menus())}

  @uweb3.decorators.loggedin
  @uweb3.decorators.checkxsrf
  def RequestCollectionSave(self, collection=None):
    """Requests the saving of changes for the given collection."""
    if not collection:
      collection = self.post.getfirst('collection', '')
    try:
      collection = self.client.CollectionFromName(collection)
    except model.Collection.NotExistError:
      return self.RequestIndex()

    if 'schema' in self.post:
      collection['schema'] = self.post.getfirst('schema')
      collection.Save()
      return self.RequestCollection(collection['name'], message="Changed saved.")

    articles = self.post.getfirst('articles', {})
    templates = self.post.getfirst('templates', {})
    urls = self.post.getfirst('urls', {})
    sort = self.post.getfirst('sort')
    prevarticles = list(collection.Articles())
    for article in prevarticles:
      if str(article['ID']) not in articles:
        article.RemoveFromCollection(collection)

    if 'name' in self.post:
      try:
        collection['name'] = self.post.getfirst('name')
        collection.Save()
      except model.InvalidNameError:
        return self.Error('Please enter a valid name for the collection', 200)
      except self.connection.IntegrityError:
        return self.Error('That name was already taken, go back, try again!', 200)
    if collection['schema']:
      jsonschema = json.loads(collection['schema'])
    for article_id in articles:
      article = self.client.Article(int(article_id))
      articlecollection = model.CollectionArticle.FromCollectionAndArticle(
          self.connection, collection, article)
      articlecollection['sortorder'] = max(0, int(sort[article_id]))
      articlecollection['url'] = urls.get(article_id, '')
      articlecollection['template'] = templates[article_id]
      articlecollection['meta'] = None;
      if collection['schema']:
        articlecollection['meta'] = json.dumps(ContentFromPost(self.post, str(article['ID'])+'_meta', jsonschema))
      try:
        articlecollection.Save()
      except self.connection.IntegrityError:
        return self.Error('That url was already used in this collection, go back, try again!', 200)
    return self.RequestCollection(collection['name'], message="Changed saved.")

  @uweb3.decorators.loggedin
  @NotExistsErrorCatcher
  @uweb3.decorators.checkxsrf
  def RequestCollectionArticles(self):
    """Adds the posted articles to the given collection."""
    collection = self.client.CollectionFromName(self.post.getfirst('collection', ''))
    collection.AddArticles(self.post.getlist('articles'))
    return self.RequestCollection(collection['name'])

  @uweb3.decorators.loggedin
  @NotExistsErrorCatcher
  @uweb3.decorators.checkxsrf
  def RequestAtomArticles(self, atom):
    """Adds the posted articles to the given atom."""
    try:
      atom = self.client.Atom(int(atom))
    except ValueError:
      return self.RequestInvalidcommand(error='There is no atom: %s' % atom)

    for article in self.post.getlist('articles'):
      try:
        article = self.client.Article(int(article))
      except ValueError:
        continue  # We will skip articles that aren't owned by the client.
      atom.AddToArticle(article['ID'])
    return self.RequestAtomExample(atom['ID'])

  @uweb3.decorators.loggedin
  @uweb3.decorators.checkxsrf
  def RequestArticleNew(self):
    """Requests the creation of a new article."""
    articlename = self.post.getfirst('name', '')
    try:
      article = model.Article.Create(self.connection,
          {'name': articlename,
           'client': int(self.client)})
    except model.InvalidNameError:
      return self.RequestInvalidcommand(
                              error='Please enter a valid name for the article')
    except self.connection.IntegrityError:
      return self.Error('That name was already taken, go back, try again!', 200)
    if 'collection' in self.post:
      try:
        article.AddToCollection(self.post.getfirst('collection'))
        return uweb3.Redirect('/collection/%s' %
            self.post.getfirst('collection'), httpcode=301)
      except Exception:
        pass
    return self.req.Redirect('/articles', httpcode=301)

  @uweb3.decorators.loggedin
  @uweb3.decorators.TemplateParser('articles.html')
  def RequestArticles(self):
    """Returns a page with the newest and most used articles."""
    toparticles = None
    articles = None
    query = self.get.getfirst('query', None)
    try:
      if query:
        articles = list(self.client.ArticleSearch(query))
      else:
        articles = list(self.client.Articles(order=[('ID', True)], limit=20))
        toparticles = list(self.client.TopArticles(limit=20))
    except model.Collection.NotExistError:
      pass
    return {'toparticles': toparticles,
            'articles': articles,
            'query': query}

  @uweb3.decorators.loggedin
  @NotExistsErrorCatcher
  @uweb3.decorators.TemplateParser('article.html')
  def RequestArticle(self, collection, article=None):
    """Returns an article"""
    if not article:
      article = collection
      collection = None
    if collection:
      collection = self.client.CollectionFromName(collection)
      article = collection.Article(article)
    else:
      article = self.client.ArticleFromName(article)
    collections = list(article.GetCollections())
    if not collection and len(collections) == 1:
      collection = collections[0]
    maxsort = 0
    atoms = None
    try:
      atoms = list(article.Atoms())
      for atom in atoms:
        maxsort = max(int(atom['sortorder']), maxsort)
    except model.Article.NotExistError:
      pass
    return {'article': article,
            'collection': collection,
            'atoms': atoms,
            'types': list(self.client.Types()),
            'collections': collections,
            'maxsort': maxsort}

  @uweb3.decorators.loggedin
  @NotExistsErrorCatcher
  def RequestArticleRemove(self, article):
    """Removes an aricle"""
    article = self.client.ArticleFromName(article)
    article.Delete()
    return self.req.Redirect('/articles', httpcode=301)

  @uweb3.decorators.loggedin
  @NotExistsErrorCatcher
  @uweb3.decorators.checkxsrf
  def RequestArticleSave(self, article):
    """Requests the saving of changes for the given article."""
    article = self.client.ArticleFromName(article)
    article['name'] = self.post.getfirst('name', '')
    try:
      article.Save()
    except model.InvalidNameError:
      return self.RequestInvalidcommand(
                              error='Please enter a valid name for the article')
    except self.connection.IntegrityError:
      return self.Error('That name was already taken, go back, try again!', 200)

    # uncouple, and recouple all atoms
    coupledatoms = self.post.getfirst('atoms', [])
    try:
      article_atoms = list(article.Atoms())
      if article_atoms:
        for atom in article_atoms:
          if (not coupledatoms or
              str(atom['ID']) not in coupledatoms):
            atom.RemoveFromArticle(article['ID'])
    except model.Article.NotExistError:
      article_atoms = []

    # process updates and new atoms.
    values = {'keys': self.post.getfirst('key', {}),
              'types': self.post.getfirst('type', None)}

    atomtypes = {}
    atomschemas = {}
    for atomtypeid in values['types'].values():
      try:
        atomtypeid = int(atomtypeid)
        if atomtypeid not in atomtypes:
          atomtype = self.client.Type(atomtypeid)
          atomtypes[atomtypeid] = atomtype
          atomschemas[atomtypeid] = json.loads(atomtype['schema'])
      except (ValueError, model.Type.NotExistError):
        return self.Error('That "%r" was not a valid Type!' % atom['type'], 404)

    if values['types']:
      for atom in article_atoms:
        if str(atom['ID']) not in values['types']:
          continue
        atom['key'] = values['keys'].get(str(atom['ID']), None)
        atom['type'] = atomtypes[int(values['types'].get(str(atom['ID']), ''))]
        atom['content'] = json.dumps(ContentFromPost(self.post, str(atom['ID']), atomschemas[atom['type']['ID']]))
        try:
          atom.Save()
          atom.SetArticlePosition(article.key, int(self.post.getfirst('sort', {}).get(str(atom['ID']), 0)))
        except self.connection.IntegrityError:
          return self.Error('That name was already taken, go back, try again!', 200)

    # handle new atoms
    newatom = {}
    newatom['key'] = values['keys'].get('new', None)
    newatom['type'] = atomtypes[int(values['types'].get('new', ''))]
    content = ContentFromPost(self.post, 'new', atomschemas[newatom['type']['ID']])
    if content:
      newatom['content'] = json.dumps(content)
      try:
        newatom = model.Atom.Create(self.connection, newatom)
        newatom.AddToArticle(article.key)
        newatom.SetArticlePosition(article.key, len(coupledatoms))
      except self.connection.IntegrityError:
        return self.Error('That name was already taken, go back, try again!', 200)

    return self.RequestArticle(article['name'])

  @uweb3.decorators.loggedin
  @NotExistsErrorCatcher
  @uweb3.decorators.TemplateParser('atom.html')
  def RequestAtomExample(self, atom):
    """Returns an Atom rendered in its template"""
    try:
      atom = self.client.Atom(int(atom))
    except ValueError:
      return self.RequestInvalidcommand(error='There is no atom: %s' % atom)
    try:
      atomfields = atom.Content()
    except ValueError:
      return self.RequestInvalidcommand('Could not render: %s' % atom)

    articles = None
    try:
      articles = list(atom.Articles())
      articlelist = []
      for article in articles:
        articlelist.append(article['ID'])
    except model.Atom.NotExistError:
      pass

    toparticles = None
    allarticles = None
    query = self.get.getfirst('query', None)
    try:
      if query:
        allarticles = list(self.client.ArticleSearch(query))
      else:
        allarticles = list(self.client.Articles(order=[('ID', True)], limit=20))
        toparticles = list(self.client.TopArticles(limit=20))
    except model.Collection.NotExistError:
      pass

    newarticles = []
    if allarticles:
      if not articles:
        newarticles = allarticles
      else:
        for article in allarticles:
          if article['ID'] not in articlelist:
            newarticles.append(article)

    return {'output': atom.Render(self.safeparser),
            'atominfo': atom,
            'atomfields': atomfields,
            'toparticles': toparticles or '',
            'allarticles': newarticles or '',
            'query': query,
            'articles': articles}

  @uweb3.decorators.loggedin
  @uweb3.decorators.checkxsrf
  def RequestMenuNew(self):
    """Requests the creation of a new menu."""
    try:
      collection = self.client.CollectionFromName(self.post.getfirst('collection', ''))
    except model.Collection.NotExistError:
      return self.RequestInvalidcommand(error='That collectiondoes not exists')
    menuname = self.post.getfirst('name', '')
    try:
      menu = model.Menu.Create(self.connection,
          {'name': menuname,
           'collection': int(collection),
           'client': int(self.client)})
    except model.InvalidNameError:
      return self.RequestInvalidcommand(
                              error='Please enter a valid name for the menu')
    except self.connection.IntegrityError:
      return self.Error('That name was already taken, go back, try again!', 200)
    return self.req.Redirect('/menus', httpcode=301)

  @uweb3.decorators.loggedin
  @uweb3.decorators.TemplateParser('menus.html')
  def RequestMenus(self):
    """Returns a page with the menus."""
    query = self.get.getfirst('query', None)
    try:
      if query:
        menus = list(self.client.MenuSearch(query))
      else:
        menus = list(self.client.Menus(limit=20))
    except model.Collection.NotExistError:
      menus = None
    return {'collections': list(self.client.Collections()),
            'menus': menus,
            'query': query}

  @uweb3.decorators.loggedin
  @NotExistsErrorCatcher
  @uweb3.decorators.TemplateParser('menu.html')
  def RequestMenu(self, collection, menu, message=None):
    """Returns a page for the menu."""
    menu = self.client.MenuFromName(collection, menu)

    articles = None
    try:
      articles = list(menu.Articles())
      articlelist = []
      for article in articles:
        articlelist.append(article['ID'])
    except model.Article.NotExistError:
      pass

    toparticles = None
    allarticles = None
    query = self.get.getfirst('query', None)
    try:
      if query:
        allarticles = list(menu['collection'].ArticleSearch(query))
      else:
        allarticles = list(menu['collection'].Articles(order=[('ID', True)], limit=20))
        toparticles = list(menu['collection'].TopArticles(limit=20))
    except model.Collection.NotExistError:
      pass

    newarticles = []
    if allarticles:
      if not articles:
        newarticles = allarticles
      else:
        for article in allarticles:
          if article['ID'] not in articlelist:
            newarticles.append(article)
    return {'menu': menu,
            'articles': articles or '',
            'toparticles': toparticles or '',
            'allarticles': newarticles or '',
            'query': query,
            'message': message}

  @uweb3.decorators.loggedin
  @uweb3.decorators.checkxsrf
  def RequestMenuSave(self, collection=None, menu=None):
    """Requests the saving of changes for the given menu."""
    if not collection:
      collection = self.post.getfirst('collection', '')
    if not menu:
      menu = self.post.getfirst('menu', '')
    articles = self.post.getfirst('articles', {})
    menunames = self.post.getfirst('menunames', {})
    sort = self.post.getfirst('sort')

    try:
      menu = self.client.MenuFromName(collection, menu)
      prevarticles = list(menu.Articles())
      for article in prevarticles:
        if str(article['ID']) not in articles:
          article.RemoveFromMenu(menu)
    except model.Menu.NotExistError:
      return self.RequestIndex()

    if 'name' in self.post:
      try:
        menu['name'] = self.post.getfirst('name')
        menu.Save()
      except model.InvalidNameError:
        return self.Error('Please enter a valid name for the menu', 200)
      except self.connection.IntegrityError:
        return self.Error('That name was already taken, go back, try again!', 200)
    for article_id in articles:
      article = self.client.Article(int(article_id))
      articlemenu = model.MenuArticle.FromMenuArticle(
          self.connection, menu, article)
      articlemenu['name'] = menunames.get(article_id, '')
      articlemenu['sortorder'] = max(0, int(sort[article_id]))
      articlemenu.Save()
    return self.RequestMenu(menu['collection']['name'], menu['name'], message="Changed saved.")

  @uweb3.decorators.loggedin
  @NotExistsErrorCatcher
  @uweb3.decorators.checkxsrf
  def RequestMenuRemove(self, collection, menu):
    """Removes the requested menu"""
    menu = self.client.MenuFromName(collection, menu)
    menu.Delete()
    return self.req.Redirect('/menus', httpcode=301)

  @uweb3.decorators.loggedin
  @NotExistsErrorCatcher
  @uweb3.decorators.checkxsrf
  def RequestMenuArticles(self):
    """Adds the posted articles to the given menu."""
    menu = self.client.MenuFromName(self.post.getfirst('collection', ''),
                                    self.post.getfirst('menu', ''))
    menu.AddArticles(self.post.getlist('articles'))
    return self.RequestMenu(menu['collection']['name'], menu['name'])

  @uweb3.decorators.loggedin
  @uweb3.decorators.checkxsrf
  @uweb3.decorators.TemplateParser('usersettings.html')
  def RequestUserSettings(self):
    """Returns the user settings page."""
    # handle password change
    if ('password' in self.post or
        'password_confirm' in self.post):
      password = self.post.getfirst('password', '')
      password_confirm = self.post.getfirst('password_confirm', '')
      if password != password_confirm:
        return {'error': 'Passwords do not match, try again.'}
      try:
        self.user.UpdatePassword(password)
      except ValueError:
        return {'error': 'Passwords too short.'}
      else:
        content = self.parser.Parse('email/updateuser.txt',
          email=self.user['email'],
          host=self.options['general']['host'],
          newpassword=password)
        try:
          with mail.MailSender(local_hostname=self.options['general']['host']) as send_mail:
            send_mail.Text(self.user['email'], 'CMS account change', content)
        except mail.SMTPConnectError:
          if not self.debug:
            return self.Error('Mail could not be send due to server error, please contact support.')
      return {'succes': 'Password has been updated.'}
    return {}


  @uweb3.decorators.loggedin
  @uweb3.decorators.checkxsrf
  @uweb3.decorators.TemplateParser('apikeys.html')
  def RequestApiKeys(self):
    """Returns the api settings page."""
    if not self.user['apiaccess']:
      return self.req.Redirect('/')

    currentkeys = list(self.client.Apiusers())

    # handle api key updates
    keys = []
    if self.post:
      deleted = self.post.getfirst('delete', {})
      updates = {'name': self.post.getfirst('name', {}),
                 'collectionfilter': self.post.getfirst('collectionfilter', {}),
                 'active': self.post.getfirst('active', {})}
      for key in currentkeys:
        keyid = str(key['ID'])
        if keyid in deleted:
          key.Delete()
        else:
          for field in ('name', 'collectionfilter'):
            if keyid in updates[field]:
              key[field] = updates[field][keyid]
          key['active'] = "false"
          if keyid in updates['active']:
            key['active'] = "true"
          key.Save()
          keys.append(key)
    else:
      keys = currentkeys

    # handle new api key creation
    if self.post and self.post.getfirst('new_name', ''):
      try:
        newkey = model.Apiuser.Create(self.connection,
          {'name': self.post.getfirst('new_name'),
           'collectionfilter': self.post.getfirst('new_filter'),
           'client': int(self.client)})
        keys.append(newkey)
      except model.InvalidNameError:
        return {'keys': keys,
                'apierror': 'Provide a valid name for the new API key.'}
      except self.connection.IntegrityError:
        return {'keys': keys,
                'apierror': 'That name was already used for another key.'}
      return {'keys': keys,
              'apisucces': 'Your new API key is: "%s".' % newkey['key']}
    return {'keys': keys}

  @uweb3.decorators.loggedin
  @NotExistsErrorCatcher
  @uweb3.decorators.checkxsrf
  def RequestVarsSave(self):
    """Requests the saving or creation of changes for variables."""
    tags = self.post.getfirst('tags')
    values = self.post.getfirst('values')
    if values and tags:
      for variableid in tags:
        variable = self.client.Variable(variableid)
        if not tags[variableid].strip():
          continue  # tags can't be spaces or empty strings.
        variable['tag'] = tags[variableid].strip()
        variable['value'] = values.get(variableid, '')
        try:
          variable.Save()
        except self.connection.IntegrityError:
          return self.Error('You already have a variable with this tag name.',
                            200, '/variables')

    if (self.post.getfirst('new_tag', '').strip() and
        self.post.getfirst('new_value', '')):
      try:
        model.Variable.Create(self.connection,
            {'tag': self.post.getfirst('new_tag').strip(),
             'value': self.post.getfirst('new_value'),
             'client': int(self.client)})
      except self.connection.IntegrityError:
        return self.Error('You already have a variable with this tag name.',
                          200, '/variables')
    return self.RequestVariables()

  @uweb3.decorators.ContentType('application/json')
  @apiuser
  def RequestCollectionJson(self, collection):
    """Returns a collection"""
    try:
      collection = self.client.CollectionFromName(collection)
    except model.Collection.NotExistError:
      return self.RequestInvalidJsoncommand('Collection: %s' % collection)
    del(collection['client'])
    del(collection['schema'])
    try:
      articlesdict = {}
      articles = list(collection.Articles())
      for article in articles:
        del(article['collection'])
        del(article['article'])
        del(article['client'])
        try:
          article['meta'] = json.loads(article['meta'])
        except (json.decoder.JSONDecodeError, TypeError) as error:
          article['meta'] = None
        articlesdict[int(article['ID'])] = article
    except model.Article.NotExistError:
      articles = []
    menus = list(collection.Menus())
    menusbyname = {}
    for menu in menus:
      try:
        menusbyname[menu['name']] = list({'ID': article['ID'], 'name': article['menuname']} for article in menu.Articles())
      except model.Article.NotExistError:
        menusbyname[menu['name']] = []
    return {
      'collection': collection,
      'menus': menusbyname,
      'articles': articlesdict}

  @uweb3.decorators.ContentType('application/json')
  @apiuser
  def RequestMenuJson(self, collection, menu):
    """Returns a menu"""
    try:
      collection = self.client.CollectionFromName(collection)
    except model.Collection.NotExistError:
      return self.RequestInvalidJsoncommand('Collection: %s' % collection)
    del(collection['client'])
    try:
      menu = collection.Menu(menu)
    except model.Menu.NotExistError:
      return self.RequestInvalidJsoncommand('Menu: %s' % menu)
    del(menu['client'])
    del(menu['collection'])
    try:
      articles = menu.Articles()
    except model.Article.NotExistError:
      articles = []
    return {
        'menu': menu,
        'articles': list(articles)}

  @uweb3.decorators.ContentType('application/json')
  @apiuser
  def RequestArticleJson(self, article, replacevars=None):
    """Returns an article, output as json"""
    raw = ('raw' in self.get)
    try:
      if replacevars:
        replacevars = json.loads(base64.decodebytes(replacevars.encode('ascii')))
    except json.decoder.JSONDecodeError:
      return self.RequestInvalidJsoncommand('Provided base64 json is incorrectly formatted.', 400)
    except binascii.Error:
      return self.RequestInvalidJsoncommand('Provided base64 has incorrect padding.', 400)
    except Exception:
      replacevars = {}
    try:
      article = self.client.ArticleFromName(article)
    except model.Article.NotExistError:
      return self.RequestInvalidJsoncommand('Article: %s' % article)

    atoms = []
    articleatoms = []
    atomsbykey = {}
    atomsbyid = {}
    del(article['client'])
    try:
      articleatoms = list(article.Atoms())
    except model.Article.NotExistError:
      return {'article': article, 'atoms': []}
    position = 0
    for atom in articleatoms:
      try:
        content = json.loads(atom['content']) if raw else atom.Render(self.safeparser)
      except json.decoder.JSONDecodeError:
        content = atom['content']
      atom['content'] = self.ReplaceVars(content, replacevars)
      atom['typename'] = atom['type']['name']
      del(atom['type'])
      listpos = position
      if atom['key']:
        atomsbykey[atom['key']] = listpos
      atomsbyid[atom.key] = listpos
      position += 1
    return {'article': article,
            'atoms': {'sort': articleatoms,
                      'key': atomsbykey,
                      'id': atomsbyid}}

  def XSRFInvalidToken(self):
    """Show that the users XSRF token is b0rked"""
    return self.Error("Your session has expired.", 403)

  def RequestInvalidcommand(self, command=None, error=None, httpcode=404):
    """Returns an error message"""
    uweb3.logging.warning('Bad page %r requested', command)
    if command is None and error is None:
      command = self.req.path
    page_data = self.parser.Parse('404.html', command=command, error=error)
    return uweb3.Response(content=page_data, httpcode=httpcode)

  @uweb3.decorators.ContentType('application/json')
  def RequestInvalidJsoncommand(self, command, httpcode=404):
    """Returns an error message"""
    uweb3.logging.warning('Bad json page %r requested', command)
    return uweb3.Response(content={'error': command}, httpcode=httpcode)

  def Error(self, error='', httpcode=500, link=None):
    """Returns a generic error page based on the given parameters."""
    uweb3.logging.error('Error page triggered: %r', error)
    page_data = self.parser.Parse('error.html', error=error, link=link)
    return uweb3.Response(content=page_data, httpcode=httpcode)

  @property
  def ReplaceVariables(self):
    """Returns the '_replacevariables' property if present.

    Gets all existing variables from the database if '_replacevariables' has not
    been set yet.
    """
    if not self._replacevariables:
      variables = self.client.Variables()
      self._replacevariables = {}
      for variable in variables:
        self._replacevariables[variable['tag']] = variable['value']
    return self._replacevariables

  def ReplaceVars(self, text, replaces):
    """Replaces tags in the given text with the replace variables.

    The replace variables are made up of all variables in 'ReplaceVariables', as
    well as optional additions in 'replaces'.
    """
    if replaces:
      replaces.update(self.ReplaceVariables)
    else:
      replaces = self.ReplaceVariables
    if isinstance(text, str):
      return self.parser.ParseString(text, **replaces)
    for key in text:
      key = self.ReplaceVars(key, replaces)
    return text

def ContentFromPost(post, atom, schema):
  try:
    if schema['type'] == 'object':
      content = ContentFromPostObject(post, atom, '', schema)
    elif schema['type'] == 'array':
      fieldname = schema.get('name', schema.get('description', 'Content'))
      content = ContentFromPostArray(post, atom, '', fieldname, schema)
    if content:
      return content
  except KeyError:
    pass
  return False

def ContentFromPostObject(post, atom, path, schema):
  content = {}
  for fieldname in schema['properties']:
    subpath = path + '_' + fieldname;
    childschema = schema['properties'][fieldname];
    if schema['properties'][fieldname]['type'] == 'array':
      data = ContentFromPostArray(post, atom, subpath, fieldname, childschema)
    elif schema['properties'][fieldname]['type'] == 'object':
      data = ContentFromPostObject(post, atom, subpath, childschema)
    else:
      data = post.getfirst(atom+subpath)
    if data:
      content[fieldname] = data
  if content:
    return content
  return False

def ContentFromPostArray(post, atom, path, fieldname, schema):
  maxcount = schema.get('maxItems', 9999)
  content = []
  for count in range(0, maxcount):
    try:
      subpath = path + '_' + str(count);
      if schema['items']['type'] == 'array':
        postdata = ContentFromPostArray(post, atom, subpath, fieldname, schema['items'])
      elif schema['items']['type'] == 'object':
        postdata = ContentFromPostObject(post, atom, subpath, schema['items'])
      else:
        postdata = post.getfirst(atom+subpath)
      if not postdata:
        break
      content.append(postdata)
    except KeyError:
      break
  if content:
    return content
  return False
