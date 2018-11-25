(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.user', ['ui.select'])
      .config(routeConfig);

  /** @ngInject */
  function routeConfig(stateExtenderProvider) {
    stateExtenderProvider.$get()
        .addState({
          name: 'user',
          title: 'User',
          template : '<ui-view autoscroll="true" autoscroll-body-top></ui-view>',
          abstract: true,
          sidebarMeta: {
            icon: 'glyphicon glyphicon-user',
            order: 7,
          },
        })
    stateExtenderProvider.$get()
        .addState({
          name: 'user.list',
          url: '/user',
          title: 'List User',
          templateUrl: 'app/pages/user/user.html',
          controller: 'UserListCtrl',
          sidebarMeta: {
            order: 0,
          },
        })
    stateExtenderProvider.$get()
        .addState({
          name: 'user.add',
          url: '/user/add',
          templateUrl: 'app/pages/user/user.form.html',
          controller: 'UserAddCtrl',
          controllerAs: 'vm',
          title: 'Add User',
          sidebarMeta: {
            order: 200,
          },
        })
    stateExtenderProvider.$get()
        .addState({
          name: 'user.edit', 
          url: '/user/edit/:user_id',
          title: 'Edit User',
          templateUrl: 'app/pages/user/user.form.html',
          controller: 'UserEditCtrl',
          controllerAs: 'vm'
        });
  }

})();
