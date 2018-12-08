(function () {
  'use strict';

  angular.module('CyBorgBackup.pages', [
    'ui.router',

    'CyBorgBackup.pages.dashboard',
    'CyBorgBackup.pages.job',
    'CyBorgBackup.pages.catalog',
    'CyBorgBackup.pages.client',
    'CyBorgBackup.pages.repository',
    'CyBorgBackup.pages.schedule',
    'CyBorgBackup.pages.policy',
    'CyBorgBackup.pages.user',
    'CyBorgBackup.pages.profile',
    'CyBorgBackup.pages.setting',
  ])
      .config(routeConfig);

  /** @ngInject */
  function routeConfig($urlRouterProvider, baSidebarServiceProvider) {
    $urlRouterProvider.otherwise('/dashboard');
  }

})();
