(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.policy', ['ui.select'])
      .config(routeConfig);

  /** @ngInject */
  function routeConfig(stateExtenderProvider) {
    stateExtenderProvider.$get()
        .addState({
          name: 'policy',
          title: 'Policy',
          template : '<ui-view autoscroll="true" autoscroll-body-top></ui-view>',
          abstract: true,
          sidebarMeta: {
            icon: 'ion-document',
            order: 3,
          },
        });
    stateExtenderProvider.$get()
        .addState({
          name: 'policy.list',
          url: '/policy',
          title: 'List Policy',
          templateUrl: 'app/pages/policy/policy.html',
          controller: 'PolicyListCtrl',
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
          name: 'policy.add',
          url: '/policy/add',
          templateUrl: 'app/pages/policy/policy.form.html',
          controller: 'PolicyAddCtrl',
          controllerAs: 'vm',
          title: 'Add Policy',
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
        })
    stateExtenderProvider.$get()
        .addState({
          name: 'policy.edit',
          url: '/policy/edit/:policy_id',
          title: 'Edit Policy',
          templateUrl: 'app/pages/policy/policy.form.html',
          controller: 'PolicyEditCtrl',
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
