(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.setting', ['ui.select'])
      .config(routeConfig);

  /** @ngInject */
  function routeConfig(stateExtenderProvider) {
    stateExtenderProvider.$get()
        .addState({
          name: 'setting',
          url: '/setting',
          title: 'Settings',
          templateUrl : 'app/pages/setting/setting.html',
          controller: 'SettingListCtrl',
          data: {
                socket: {
                    groups: {
                        jobs: ['status_changed'],
                    }
                }
            },
          sidebarMeta: {
            icon: 'glyphicon glyphicon-wrench',
            order: 8,
          },
        });
  }

})();
