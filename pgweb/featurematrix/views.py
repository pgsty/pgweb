from copy import deepcopy
from pathlib import Path
import logging

from django.http import Http404, HttpResponseRedirect
from django.template.defaultfilters import slugify
import yaml

from pgweb.util.contexts import render_pgweb
from pgweb.util.decorators import content_sources
from pgweb.util.decorators import xkey

from pgweb.core.models import Version


log = logging.getLogger(__name__)


def compute_version_columns(versionspec, versions):
    currval = 'No'
    verspec = dict(versionspec)
    ordered = list(verspec.items())
    index = 0
    lookfor, lookforval = ordered[index]

    for ver in versions:
        if versionspec and ver.treestring == lookfor:
            currval = lookforval
            index += 1
            if index < len(ordered):
                lookfor, lookforval = ordered[index]
            else:
                lookfor, lookforval = (None, None)
        yield currval.lower()[:3]


class FeatureMatrixData:
    def __init__(self):
        root = Path(__file__).resolve().parents[2]
        self.base_fn = root / 'data' / 'featurematrix.yaml'
        self.translation_fn = root / 'data' / 'featurematrix_zh.yaml'
        self.load()

    def _mtime_signature(self):
        files = [self.base_fn, self.translation_fn]
        return tuple(
            (str(path), path.stat().st_mtime if path.exists() else None)
            for path in files
        )

    def load(self):
        self.lastload = self._mtime_signature()

        with self.base_fn.open() as f:
            self.data = yaml.safe_load(f)

        self.translations = {'groups': {}, 'features': {}}
        if self.translation_fn.exists():
            with self.translation_fn.open() as f:
                translation = yaml.safe_load(f) or {}
            self.translations['groups'].update(translation.get('groups', {}) or {})
            for name, item in (translation.get('features', {}) or {}).items():
                self.translations['features'][name.rstrip()] = item or {}

        self.featuremap = {}
        self.slugmap = {}
        for features in self.data['featurematrix'].values():
            for feature in features:
                name = feature['name'].rstrip()
                feature['name'] = name
                self.featuremap[name] = feature
                self.slugmap[slugify(name)] = name

        self.legacymap = {
            int(featureid): slugify(title.rstrip())
            for featureid, title in (self.data.get('legacymap', {}) or {}).items()
        }

    def _conditional_load(self):
        current = self._mtime_signature()
        if current != self.lastload:
            log.info("Feature matrix data has changed, reloading")
            self.load()

    def _translated_feature(self, feature):
        source_name = feature['name'].rstrip()
        translation = self.translations['features'].get(source_name, {})
        translated = deepcopy(feature)
        translated['source_name'] = source_name
        translated['slug'] = slugify(source_name)
        translated['display_name'] = translation.get('name') or source_name
        translated['display_description'] = (
            translation.get('description') or feature.get('description') or ''
        )
        return translated

    def get_groups(self):
        self._conditional_load()

        groups = []
        for group_name, features in self.data['featurematrix'].items():
            groups.append({
                'source_name': group_name,
                'slug': slugify(group_name),
                'display_name': self.translations['groups'].get(group_name, group_name),
                'features': [self._translated_feature(feature) for feature in features],
            })
        return groups

    def feature_from_slug(self, slug):
        self._conditional_load()
        feature_name = self.slugmap.get(slug)
        if not feature_name:
            return None
        return self._translated_feature(self.featuremap[feature_name])

    def get_versions(self):
        self._conditional_load()
        return self.data['versions']['min'], self.data['versions']['max']

    def slug_from_legacy(self, featureid):
        self._conditional_load()
        return self.legacymap.get(featureid)


matrixdata = FeatureMatrixData()


@xkey('data_featurematrix')
@content_sources('style', "'unsafe-inline'")
def root(request):
    minver, maxver = matrixdata.get_versions()

    versions = list(Version.objects.filter(tree__gte=minver, tree__lte=maxver).order_by('-tree'))
    versions_rev = list(reversed(versions))

    groups = matrixdata.get_groups()
    # Compute the column values on each load of the page, since the list of versions may have changed.
    # (the page is cached so it's not as bad as it sounds)
    for group in groups:
        for feature in group['features']:
            feature['columns'] = reversed(list(compute_version_columns(feature['versions'], versions_rev)))

    return render_pgweb(request, 'about', 'featurematrix/featurematrix.html', {
        'groups': groups,
        'versions': versions,
    })


@xkey('data_featurematrix')
def detail(request, featureslug):
    feature = matrixdata.feature_from_slug(featureslug)
    if not feature:
        raise Http404()
    return render_pgweb(request, 'about', 'featurematrix/featuredetail.html', {
        'feature': feature,
    })


@xkey('data_featurematrix')
def detail_legacy(request, featureid):
    # For now, provide a redirect on the old numeric URLs. We can eventually remove this, but let's
    # leave it for a while.
    slug = matrixdata.slug_from_legacy(int(featureid))
    if slug:
        return HttpResponseRedirect("../{}/".format(slug))
    raise Http404()
