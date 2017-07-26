import webapp2
import os
import sys
import jinja2
from google.appengine.ext import ndb
from google.appengine.api import users

from tweet_auths import OAuthAccessToken
from tweet_auths import CONSUMER_KEY
from tweet_auths import CONSUMER_SECRET

########################################################################
# The following is necessary to make SSL work when running locally
########################################################################

def is_development_server():
    """Use environment variable to test if this is the development
    server.

    """
    return os.environ['APPLICATION_ID'].startswith('dev~')

# See http://stackoverflow.com/a/24066819/500584.
if is_development_server():
    from google.appengine.tools.devappserver2.python import sandbox
    sandbox._WHITE_LIST_C_MODULES += ['_ssl', '_socket']
    # stdlib_socket.py is a local copy of socket.py, since that
    # library is overridden by the AppEngine version.
    import stdlib_socket
    sys.modules['socket'] = stdlib_socket
########################################################################
# End of Hack to make it work locally
########################################################################

import tweepy

env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))

class MainHandler(webapp2.RequestHandler):
    def get(self):
        template = env.get_template('templates/main.html')
        current_user = users.get_current_user()
        if not current_user:
            self.response.write(template.render({
                'login_url': users.create_login_url('/'),
            }))
        else:
            self.response.write(template.render({
                'logout_url': users.create_logout_url('/'),
            }))


class TweetsPage(webapp2.RequestHandler):

    def get(self):
        # If the user is not authenticated with Google just send them to
        # authenticate with google first.
        current_user = users.get_current_user()
        if not current_user:
            self.redirect(users.create_login_url('/list_tweets'))
            return

        # We need to build the authorization request, it's made of
        # Application keys, which come from the tweet_auths.py, and the
        # access token that we should have already received and stored
        # in datastore.
        auth = tweepy.OAuthHandler(CONSUMER_KEY, CONSUMER_SECRET)
        access_token = OAuthAccessToken.query(
                OAuthAccessToken.user_id == current_user.user_id()
                ).get()
        if not access_token:
            # If we don't have an access token yet, send the user to get one.
            # They'll go back to the homepage once they're done.
            self.redirect('/authorize_twitter')
            return
        # Otherwise we're good to go, we can set the access token which we
        # found in datastore, and send our queries to twitter to retrieve the
        # user data.
        auth.set_access_token(access_token.token, access_token.token_secret )

        api = tweepy.API(auth)

        # The following part can be any twitter query that is supported by
        # the tweepy API. In this example we get 10 tweets by Taylor swift.
        stuff = api.user_timeline(
            screen_name = 'taylorswift13',
            count = 10,
            include_rts = True)

        # We'll store the data in a dictionary, and use a template to render
        # it nicely.
        variables = {
            'name': 'taylorswift13',
            'tweets': [status.text for status in stuff]
        }
        template = env.get_template('templates/tweets_list.html')
        self.response.write(template.render(variables))

app = webapp2.WSGIApplication([
    ('/list_taytay_tweets', TweetsPage),
    ('/', MainHandler),
], debug=True)
