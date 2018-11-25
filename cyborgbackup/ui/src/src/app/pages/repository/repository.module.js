(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.repository', [])
      .config(routeConfig);

  /** @ngInject */
  function routeConfig(stateExtenderProvider) {
    stateExtenderProvider.$get()
        .addState({
          name: 'repository',
          title: 'Repository',
          template : '<ui-view autoscroll="true" autoscroll-body-top></ui-view>',
          abstract: true,
          sidebarMeta: {
            icon: 'ion-cube',
            order: 5,
          },
        });
    stateExtenderProvider.$get()
        .addState({
          name: 'repository.list', 
          url: '/repository',
          title: 'List Repository',
          templateUrl: 'app/pages/repository/repository.html',
          controller: 'RepositoryListCtrl',
          sidebarMeta: {
            order: 0,
          },
        });
    stateExtenderProvider.$get()
        .addState({
          name: 'repository.add',
          url: '/repository/add',
          templateUrl: 'app/pages/repository/repository.form.html',
          controller: 'RepositoryAddCtrl',
          controllerAs: 'vm',
          title: 'Add Repository',
          sidebarMeta: {
            order: 200,
          },
        });
    stateExtenderProvider.$get()
        .addState({
          name: 'repository.edit',
          url: '/repository/edit/:repository_id',
          title: 'Edit Repository',
          templateUrl: 'app/pages/repository/repository.form.html',
          controller: 'RepositoryEditCtrl',
          controllerAs: 'vm'
        });
  }

})();
