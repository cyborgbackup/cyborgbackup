(function () {
  'use strict';

  angular.module('CyBorgBackup.theme')
      .service('baAuthentication', baAuthentication);

  /** @ngInject */
  function baAuthentication($http, $rootScope, $cookies, GetBasePath, SocketService, Store, $q, $injector) {
    this.setToken = function (token, expires) {
        $cookies.remove('token_expires');
        $cookies.remove('userLoggedIn');

        $cookies.put('token_expires', expires);
        $cookies.put('userLoggedIn', true);
        $cookies.put('sessionExpired', false);

        $rootScope.userLoggedIn = true;
        $rootScope.token_expires = expires;
        $rootScope.sessionExpired = false;
    };

    this.isUserLoggedIn = function () {
        if ($rootScope.userLoggedIn === undefined) {
            // Browser refresh may have occurred
            $rootScope.userLoggedIn = ($cookies.get('userLoggedIn') === 'true');
            $rootScope.sessionExpired = ($cookies.get('sessionExpired') === 'true');
        }
        return $rootScope.userLoggedIn;
    };

    this.retrieveToken = function (username, password) {
        var getCSRFToken = $http({
            method: 'GET',
            url: '/api/login/'
        });
        return getCSRFToken.then(function(data) {
            var csrfmiddlewaretoken = /name='csrfmiddlewaretoken' value='([0-9a-zA-Z]+)' \//.exec(data.data)[1];
            return $http({
                method: 'POST',
                url: '/api/login/',
                data: 'username='+encodeURIComponent(username)+'&password='+encodeURIComponent(password)+'&csrfmiddlewaretoken='+csrfmiddlewaretoken+'&next=%2fapi%2f',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded'
                }
            });
        });
    };

    this.deleteToken = function () {
        return $http({
            method: 'GET',
            url: '/api/logout/'
        });
    };

    this.logout = function () {
        // the following puts our primary scope up for garbage collection, which
        // should prevent content flash from the prior user.

        var x,
        deferred = $q.defer(),
        //ConfigService = $injector.get('ConfigService'),
        SocketService = $injector.get('SocketService'),
        scope = angular.element(document.getElementById('main-view')).scope();

        this.deleteToken().then(function(){
            if(scope){
                scope.$destroy();
            }

            if($cookies.get('lastPath')==='/portal'){
                $cookies.put( 'lastPath', '/portal');
                $rootScope.lastPath = '/portal';
            }
            else if ($cookies.get('lastPath') !== '/home' || $cookies.get('lastPath') !== '/' || $cookies.get('lastPath') !== '/login' || $cookies.get('lastPath') !== '/logout'){
                // do nothing
                $rootScope.lastPath = $cookies.get('lastPath');
            }
            else {
                // your last path was home
                $cookies.remove('lastPath');
                $rootScope.lastPath = '/home';
            }
            x = Store('sessionTime');
            if ($rootScope.current_user && x && x[$rootScope.current_user.id]) {
                x[$rootScope.current_user.id].loggedIn = false;
            }
            Store('sessionTime', x);

            if ($cookies.getObject('current_user')) {
                $rootScope.lastUser = $cookies.getObject('current_user').id;
            }
            //ConfigService.delete();
            SocketService.disconnect();
            $cookies.remove('token_expires');
            $cookies.remove('current_user');
            $cookies.put('userLoggedIn', false);
            $cookies.put('sessionExpired', false);
            $cookies.putObject('current_user', {});
            $rootScope.current_user = {};
            $rootScope.userLoggedIn = false;
            $rootScope.sessionExpired = false;
            $rootScope.token_expires = null;
            $rootScope.login_username = null;
            $rootScope.login_password = null;
            if ($rootScope.sessionTimer) {
                $rootScope.sessionTimer.clearTimers();
            }
            window.location = '/auth.html';
            deferred.resolve();
        });

        return deferred.promise;

    };

    this.getUser = function () {
        return $http({
            method: 'GET',
            url: GetBasePath('me')
        });
    };

    this.setUserInfo = function (response) {
        // store the response values in $rootScope so we can get to them later
        $rootScope.current_user = response.results[0];
        $cookies.putObject('current_user', response.results[0]); //keep in session cookie in the event of browser refresh
    };

    this.restoreUserInfo = function () {
        $rootScope.current_user = $cookies.getObject('current_user');
    };

    this.getUserInfo = function (key) {
        // Access values returned from the Me API call
        var cu;
        if ($rootScope.current_user) {
            return $rootScope.current_user[key];
        }
        this.restoreUserInfo();
        cu = $cookies.getObject('current_user');
        return cu[key];
    };
  };
})();
