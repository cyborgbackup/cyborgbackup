'use strict';

angular.module('CyBorgBackup', [
  'ngAnimate',
  'ui.bootstrap',
  'ui.sortable',
  'ui.router',
  'ngTouch',
  'toastr',
  'smart-table',
  "xeditable",
  'ui.slimscroll',
  'ngJsTree',
  'angular-duration-format',
  'angular-cron-gen',
  'angular-progress-button-styles',
  'CyBorgBackup.RestServices',
  'CyBorgBackup.utils',
  'CyBorgBackup.theme',
  'CyBorgBackup.pages'
])
.constant("moment", moment)
.constant('_', _)
.config(['$logProvider', '$stateProvider', function($logProvider, $stateProvider) {
  $logProvider.debugEnabled(true);
  $stateProvider
      .state('signOut', {
        url: '/logout',
        title: 'Logout',
        controller: function($scope, baAuthentication){
          if(baAuthentication.isUserLoggedIn()){
            baAuthentication.logout();
            window.location = '/auth.html';
          }
        }
      });
}])
.filter('settingName', function(){
    return function(input){
        names = input.replace('cyborgbackup_', '').split('_')
        for(var i=0; i<names.length; i++){ names[i] = names[i].replace(/^\w/, c => c.toUpperCase()); }
        return names.join(' ');
    };
})
.filter('humanSize', function(){
     return function(size){
         if(isNaN(size)){ return '';}
         var i = Math.floor( Math.log(size) / Math.log(1024) );
         return ( size / Math.pow(1024, i) ).toFixed(2) * 1 + ' ' + ['B', 'kB', 'MB', 'GB', 'TB'][i];
     };
})
.filter('longDate', function() {
         return function(input) {
            var date;
             if(input === null || input === undefined){
                 return "";
             }else {
                 date = moment(input);
                 return date.format('l LTS');
             }
         };
     })
.directive('logout', logoutMethod)
.run(themeRun);

function logoutMethod(baAuthentication, $state) {
  return {
    restrict: 'A',
    link: function(scope, elem) {
      elem.on('click', function($evt) {
        $evt.originalEvent.$sidebarEventProcessed = true;
        scope.$apply(function() {
            $state.go('signOut')
        });
      });
    }
  };
}

/** @ngInject */
function themeRun($timeout, $rootScope, $location, layoutPaths, preloader, $q, baSidebarService, LoadBasePaths, baAuthentication, SocketService, toastr, Timer, Wait, Alert, themeLayoutSettings) {
  LoadBasePaths();
  var whatToWait = [
    preloader.loadAmCharts(),
    $timeout(2000)
  ];

  $rootScope.logout = function(){
    console.log('Want logout');
  }

  var theme = themeLayoutSettings;
  if (theme.blur) {
    if (theme.mobile) {
      whatToWait.unshift(preloader.loadImg(layoutPaths.images.root + 'blur-bg-mobile.jpg'));
    } else {
      whatToWait.unshift(preloader.loadImg(layoutPaths.images.root + 'blur-bg.jpg'));
      whatToWait.unshift(preloader.loadImg(layoutPaths.images.root + 'blur-bg-blurred.jpg'));
    }
  }

  $q.all(whatToWait).then(function () {
    $rootScope.$pageFinishedLoading = true;
  });

  if(!baAuthentication.isUserLoggedIn())
  {
     window.location = '/auth.html';
  }else{
    baAuthentication.getUser()
      .then(({data}) => {
          baAuthentication.setUserInfo(data);
          Timer.init().then(function(timer){
              $rootScope.sessionTimer = timer;
              SocketService.init();
              $rootScope.user_is_superuser = data.results[0].is_superuser;
          });
      })
      .catch(({data, status}) => {
          baAuthentication.logout().then( () => {
              Wait('stop');
              Alert('Error', 'Failed to access user information. GET returned status: ' + status, 'alert-danger', loginAgain);
          });
      });
    $timeout(function () {
      if (!$rootScope.$pageFinishedLoading) {
        $rootScope.$pageFinishedLoading = true;
      }
    }, 7000);

    $rootScope.$on(`ws-jobs`, function(e, data) {
        if (parseInt(data.job_id, 10)) {
            if (data.status === "running") {
                toastr.info("Backup job "+ data.job_id + " " + data.job_name + " running")
            } else if (data.status === "successful" ) {
                toastr.success("Backup job "+ data.job_id + " " + data.job_name + " success")
            } else if (
              data.status === "failed" ||
              data.status === "error") {
                toastr.warning("Backup job "+ data.job_id + " " + data.job_name + " failed")
            }
        }
    });

    $rootScope.$baSidebarService = baSidebarService;
  }
}
