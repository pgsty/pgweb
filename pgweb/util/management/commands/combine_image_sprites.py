from django.core.management.base import BaseCommand

from pgweb.util.sprites import sprites


class Command(BaseCommand):
    help = '将图像合并为精灵图'

    def add_arguments(self, parser):
        parser.add_argument('image', type=str, nargs='?', default='all', choices=('books', 'all', ))

    def handle(self, *args, **options):
        if options['image'] == 'all':
            for k, s in sprites.items():
                self.stdout.write("正在生成 {} 精灵图".format(k))
                s.build_sprite_image()
        else:
            sprites[options['image']].build_sprite_image()
