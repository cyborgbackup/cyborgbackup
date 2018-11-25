(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.catalog', ['ui.select'])
      .config(routeConfig)
      .config(function(){
        $.jstree.defaults.core.themes.url = true;
        $.jstree.defaults.core.themes.dir = "assets/img/theme/vendor/jstree/dist/themes";
      });

  /** @ngInject */
  function routeConfig(stateExtenderProvider) {
    stateExtenderProvider.$get()
        .addState({
          name: 'catalog',
          url: '/catalog',
          title: 'Catalog',
          templateUrl : 'app/pages/catalog/catalog.html',
          controller: 'CatalogListCtrl',
          data: {
                socket: {
                    groups: {
                        jobs: ['status_changed'],
                    }
                }
            },
          sidebarMeta: {
            icon: 'glyphicon glyphicon-book',
            order: 2,
          },
        });
  }

})();
