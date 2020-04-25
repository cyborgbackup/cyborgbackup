'use strict';

var path = require('path');
var gulp = require('gulp');
var conf = require('./conf');

var browserSync = require('browser-sync');

function isOnlyChange(event) {
  return event.type === 'changed';
}

gulp.task('deploy', function(){
  gulp.src(path.join(conf.paths.src, "/app/**/*.html"))
    .pipe(gulp.dest(path.join(conf.paths.src, '../../static/')));
  gulp.src(path.join(conf.paths.devDist, "/*"), {base:"."})
    .pipe(gulp.dest(path.join(conf.paths.src, '../../static/')));
  gulp.src(path.join(conf.paths.src, "../bower_components/*"), {base:"."})
    .pipe(gulp.dest(path.join(conf.paths.src, '../../static/')));
  gulp.src(path.join(conf.paths.src, "app/*"), {base:"."})
    .pipe(gulp.dest(path.join(conf.paths.src, '../../static/')));
  gulp.src(path.join(conf.paths.src, "../../static/index.html"))
    .pipe(gulp.dest(path.join(conf.paths.src, '../../../templates/ui/')));
  gulp.src(path.join(conf.paths.src, "../../static"), {base:"."})
    .pipe(gulp.dest(path.join(conf.paths.src, '../../../static/')));
})

gulp.task('watch', ['inject'], function () {

  gulp.watch([path.join(conf.paths.src, '/*.html'), 'bower.json'], ['inject-reload']);

  gulp.watch([
    path.join(conf.paths.src, '/sass/**/*.css'),
    path.join(conf.paths.src, '/sass/**/*.scss')
  ], function(event) {
    if(isOnlyChange(event)) {
      gulp.start('styles-reload');
    } else {
      gulp.start('inject-reload');
    }
  });

  gulp.watch(path.join(conf.paths.src, '/app/**/*.js'), function(event) {
    if(isOnlyChange(event)) {
      gulp.start('scripts-reload');
    } else {
      gulp.start('inject-reload');
    }
  });

  gulp.watch(path.join(conf.paths.src, '/app/**/*.html'), function(event) {
    browserSync.reload(event.path);
  });
});
