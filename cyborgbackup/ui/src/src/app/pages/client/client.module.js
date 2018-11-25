(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.client', [])
      .config(routeConfig);

  /** @ngInject */
  function routeConfig(stateExtenderProvider) {
    stateExtenderProvider.$get()
        .addState({
          name: 'client',
          title: 'Client',
          template : '<ui-view autoscroll="true" autoscroll-body-top></ui-view>',
          abstract: true,
          sidebarMeta: {
            icon: 'ion-android-desktop',
            order: 3,
          },
        });
    stateExtenderProvider.$get()
        .addState({
          name: 'client.list',
          url: '/client',
          title: 'List Client',
          templateUrl: 'app/pages/client/client.html',
          controller: 'ClientListCtrl',
          data: {
                socket: {
                    groups: {
                        jobs: ['status_changed'],
                    }
                }
            },
          sidebarMeta: {
            order: 0,
          },
        });
    stateExtenderProvider.$get()
        .addState({
          name: 'client.add',
          url: '/client/add',
          templateUrl: 'app/pages/client/client.form.html',
          controller: 'ClientAddCtrl',
          controllerAs: 'vm',
          title: 'Add Client',
          data: {
                socket: {
                    groups: {
                        jobs: ['status_changed'],
                    }
                }
            },
          sidebarMeta: {
            order: 200,
          },
        });
    stateExtenderProvider.$get()
        .addState({
          name: 'client.edit',
          url: '/client/edit/:client_id',
          title: 'Edit Client',
          templateUrl: 'app/pages/client/client.form.html',
          controller: 'ClientEditCtrl',
          data: {
                socket: {
                    groups: {
                        jobs: ['status_changed'],
                    }
                }
            },
          controllerAs: 'vm'
        });
  }

})();
