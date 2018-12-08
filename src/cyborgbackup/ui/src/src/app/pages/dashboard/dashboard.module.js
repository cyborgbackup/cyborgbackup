(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.dashboard', [])
      .config(routeConfig);

  /** @ngInject */
  function routeConfig(stateExtenderProvider) {
    stateExtenderProvider.$get()
        .addState({
          name: 'dashboard',
          url: '/dashboard',
          templateUrl: 'app/pages/dashboard/dashboard.html',
          title: 'Dashboard',
          data: {
                socket: {
                    groups: {
                        jobs: ['status_changed'],
                    }
                }
            },
          sidebarMeta: {
            icon: 'ion-android-home',
            order: 0,
          },
        });
  }

})();
