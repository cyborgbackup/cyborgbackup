(function () {
  'use strict';

  angular.module('CyBorgBackup.login')
    .controller('LoginPageCtrl', LoginPageCtrl);

  /** @ngInject */
  function LoginPageCtrl($rootScope, $cookies, $scope, Wait, Empty, baAuthentication) {
    var vm = this;

   $scope.sessionExpired = (Empty($rootScope.sessionExpired)) ? $cookies.get('sessionExpired') : $rootScope.sessionExpired;
   $scope.login_username = '';
   $scope.login_password = '';


    $('#inputPassword3').bind('keypress', function (e) {
        var code = (e.keyCode ? e.keyCode : e.which);
        if (code === 13) {
            $('#login-button').click();
        }
    });

    $scope.reset = function () {
        $('#login-form input').each(function () {
            $(this).val('');
        });
    };

    $scope.systemLogin = function(username, password){
        $('.api-error').empty();
        if (Empty(username) || Empty(password)) {
            $scope.reset();
            $scope.attemptFailed = true;
            $('#inputEmail3').focus();
        } else {
            Wait('start');
            baAuthentication.retrieveToken(username, password)
            .then(function (data) {
                baAuthentication.setToken(data.data.expires);
                window.location = '/';
            },
            function (data) {
                var key;
                Wait('stop');
                if (data && data.data && data.data.non_field_errors && data.data.non_field_errors.length === 0) {
                    // show field specific errors returned by the API
                    for (key in data.data) {
                        $scope[key + 'Error'] = data.data[key][0];
                    }
                } else {
                    $scope.reset();
                    $scope.attemptFailed = true;
                    $('#inputEmail3').focus();
                }
            });
        }
    }
  }

})();
