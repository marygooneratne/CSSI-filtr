import webapp2
import os
import sys
import jinja2
from google.appengine.ext import ndb
from google.appengine.api import users


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

# These are the App KEY and SECRET, obtained by registering the app
# at: https://apps.twitter.com/
CONSUMER_KEY = "tNTHECGMVgP9IblPzRDOhKmZq"
CONSUMER_SECRET = "jlyB72qnCRnXRG9Rd71v4tCDYceAycX8NPENXg3bcmoHZhnb1U"

if is_development_server():
    CALLBACK = 'http://localhost:8080/oauth/callback'
else:
    CALLBACK = 'https://test-166000.appspot.com/oauth/callback'

env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))


# DataStore models for the Requests
class OAuthRequestToken(ndb.Model):
    token = ndb.StringProperty(required=True)
    token_secret = ndb.StringProperty(required=True)


class OAuthAccessToken(ndb.Model):
    user_id = ndb.StringProperty(required=True)
    token = ndb.StringProperty(required=True)
    token_secret = ndb.StringProperty(required=True)



class AuthorizeTweeterHandler(webapp2.RequestHandler):
    def get(self):
        """ First step of authentication is creating a request token,
        storing it for later, and redirecting the user to the twitter
        authorization page.
        """

        # If the user is not authenticated with Google we are going to incur
        # into problems later, so we shouldn't even continue to authenticate
        # with Twitter. Just send them to authenticate with google first.
        current_user = users.get_current_user()
        if not current_user:
            self.redirect(users.create_login_url('/'))
            return

        # If we're here it means that we are  authenticated with Google, time
        # to create a request token for authorizing the app with Twitter.
        auth = tweepy.OAuthHandler(CONSUMER_KEY, CONSUMER_SECRET, CALLBACK)
        authorization_url = auth.get_authorization_url()

        # We will only be sending the request token key, but not the secret.
        # That much we'll have to store it locally and use it for the second
        # step of the authentication.
        request_token = OAuthRequestToken(
                token = auth.request_token['oauth_token'],
                token_secret = auth.request_token['oauth_token_secret']
        )
        request_token.put()

        # Let's send the user to twitter now, they'll come back to the
        # callback handler, defined in CALLBACK, once they are authenticated.
        # The URL is returned as a unicode string, but we must use a regular
        # string here, so we convert it using "str()"
        self.redirect(str(authorization_url))

class CallbackPage(webapp2.RequestHandler):

    def get(self):
        """ Second step of authentication, once the user has clicked on
        Authorize in the twitter page, they come back here, give us the
        request token and the verifier token, and we will use them to
        finally get our access token, which will be valid until the user
        revokes it.
        """

        # We need to know that the user is logged in through google, since
        # we will use this to identify them for everything from now on.
        current_user = users.get_current_user()
        if not current_user:
            self.redirect(users.create_login_url('/'))
            return

        # In the callback itself, twitter is sending us two values, the
        # request token key that we sent before, and the oauth_verifier
        # token.
        oauth_token = self.request.get("oauth_token", None)
        oauth_verifier = self.request.get("oauth_verifier", None)

        # We lookup the request token to find the corresponding secret, which
        # we stored before.
        request_token = OAuthRequestToken.query(
                OAuthRequestToken.token==oauth_token).get()

        # We should always find it in our storage, since it should alwas come
        # as the second phase, but just in case, we'll throw an error if we
        # cannot find it.
        if request_token is None:
            template = env.get_template("templates/error.html")
            self.response.write(template.render({'message': 'Invalid token!'}))
            return

        # Rebuild the auth handler, this time with the request token key and
        # secret that we had from before.
        auth = tweepy.OAuthHandler(CONSUMER_KEY, CONSUMER_SECRET)
        auth.request_token = {
                'oauth_token' : request_token.token,
                'oauth_token_secret': request_token.token_secret
                }

        # We should not need the request token any longer since we now have
        # the access token. So we can delete it from the datastore, if necessary
        # we will obtain a new one from Step 1.
        request_token.key.delete()
        # With all the info we have now, we can finally fetch the access token
        # from twitter. This will grant us access to the user's tweeter account
        # from now on.
        try:
            auth.get_access_token(oauth_verifier)
        except tweepy.TweepError, e:
            # Hopefully we'll never see an error, but it's better to be
            # prepared just in case.
            template = env.get_template("templates/error.html")
            self.response.write(template.render('error.html', {'message': e}))
            return

        # So now we could use this auth handler. But the real thrill is that
        # we can store it in datastore, asssociated with our google user id,
        # and use it forever from now on. The only issue with this approach
        # is that one google user is forever bound to its tweeter accont, we
        # cannot have multiple identities, but that'll do for now.

        # Let's see if we have already an access token for this google user,
        # who knows, maybe we're just updating it.
        access_token = OAuthAccessToken.query(
                OAuthAccessToken.user_id == current_user.user_id()
                ).get()
        if not access_token:
            # Never got access to this user's tweets yet, we're creating a new
            # entry for them.
            access_token = OAuthAccessToken(
                    user_id = current_user.user_id(),
                    token = auth.access_token,
                    token_secret = auth.access_token_secret
            )
        else:
            # We had already one entry for the user, but we need to update
            # their values.
            access_token.token = auth.access_token
            access_token.token_secret = auth.access_token_secret

        access_token.put()
        # Let's send the user back to the home page now that we are authorized.
        self.redirect("/")


app = webapp2.WSGIApplication([
    ('/authorize_twitter', AuthorizeTweeterHandler),
    ('/oauth/callback', CallbackPage),
], debug=True)
