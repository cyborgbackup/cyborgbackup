(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.schedule', [])
      .config(routeConfig);

  /** @ngInject */
  function routeConfig(stateExtenderProvider) {
    stateExtenderProvider.$get()
        .addState({
          name: 'schedule',
          title: 'Schedule',
          template : '<ui-view autoscroll="true" autoscroll-body-top></ui-view>',
          abstract: true,
          sidebarMeta: {
            icon: 'ion-android-time',
            order: 6,
          },
        });
    stateExtenderProvider.$get()
        .addState({
          name: 'schedule.list',
          url: '/schedule',
          title: 'List Schedule',
          templateUrl: 'app/pages/schedule/schedule.html',
          controller: 'ScheduleListCtrl',
          sidebarMeta: {
            order: 0,
          },
        });
    stateExtenderProvider.$get()
        .addState({
          name: 'schedule.add',
          url: '/schedule/add',
          templateUrl: 'app/pages/schedule/schedule.form.html',
          controller: 'ScheduleAddCtrl',
          controllerAs: 'vm',
          title: 'Add Schedule',
          sidebarMeta: {
            order: 200,
          },
        });
    stateExtenderProvider.$get()
        .addState({
          name: 'schedule.edit', 
          url: '/schedule/edit/:schedule_id',
          title: 'Edit Schedule',
          templateUrl: 'app/pages/schedule/schedule.form.html',
          controller: 'ScheduleEditCtrl',
          controllerAs: 'vm'
        });
  }

})();
