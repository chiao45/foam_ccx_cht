import numpy as np
from pydtk2 import *
from pymoab.core import Core
from pymoab.types import MB_TYPE_DOUBLE, MB_TAG_DENSE, MBVERTEX


dim = 3


class Mapper:
    def __init__(self, dtk, moab, str2tag, vs):
        self.dtk = dtk
        self.moab = moab
        self.str2tag = str2tag
        self.vrange = vs

    def put(self, tag, data):
        self.moab[0].tag_set_data(self.str2tag[0][tag], self.vrange[0], data)

    def get(self, tag):
        return self.moab[1].tag_get_data(
            self.str2tag[1][tag], self.vrange[1], True)

    def apply(self, src, tgt):
        self.dtk.apply(src, tgt)


def mesh_manager(coord, tags):
    if coord.shape[1] == 2:
        temp = np.zeros(
            shape=(coord.shape[0], 3), dtype=float
        )
        temp[:, 0:2] = coord
        coord = temp
    mdb = Core()
    verts = mdb.create_vertices(coord.flatten())
    tags_ = {}
    for tag in tags:
        tags_[tag] = mdb.tag_get_handle(
            tag,
            size=1,
            tag_type=MB_TYPE_DOUBLE,
            storage_type=MB_TAG_DENSE,
            create_if_missing=True
        )
        mdb.tag_set_data(tags_[tag], verts, np.zeros(coord.shape[0]))
    dtkmnr = DTK2MoabManager(mdb)
    dtkmnr.register_tags(tags)
    return dtkmnr, mdb, tags_, verts


def generate_mapper(fluid_coord, solid_coord, f2s_tag_dict, s2f_tag_dict, r1=0.2, r2=0.1):
    ftags = []
    stags = []
    for f, s in f2s_tag_dict.items():
        ftags.append(f)
        stags.append(s)
    for s, f in s2f_tag_dict.items():
        if s not in stags:
            stags.append(s)
        if f not in ftags:
            ftags.append(f)

    if not isinstance(solid_coord, list):
        solid_coord = [solid_coord]

    smdb = []
    moabs = []
    str2tags = []
    vertss = []

    fmdb, moabf, str2tagf, vertsf = mesh_manager(fluid_coord, ftags)
    for sc in solid_coord:
        a, b, c, d = mesh_manager(sc, stags)
        smdb.append(a)
        moabs.append(b)
        str2tags.append(c)
        vertss.append(d)

    f2s_mapper = DTK2Mapper(source=fmdb, target=smdb[0], r=r1)
    s2f_mapper = DTK2Mapper(source=smdb[-1], target=fmdb, r=r2)

    f2s_mapper.set_spacial_dimension(dim)
    s2f_mapper.set_spacial_dimension(dim)

    for f, s in f2s_tag_dict.items():
        f2s_mapper.register_coupled_tags(f, s)
    for s, f in s2f_tag_dict.items():
        s2f_mapper.register_coupled_tags(s, f)

    f2s = Mapper(
        dtk=f2s_mapper,
        moab=[moabf, moabs[0]],
        str2tag=[str2tagf, str2tags[0]],
        vs=[vertsf, vertss[0]]
    )
    s2f = Mapper(
        dtk=s2f_mapper,
        moab=[moabs[-1], moabf],
        str2tag=[str2tags[-1], str2tagf],
        vs=[vertss[-1], vertsf]
    )

    return (f2s, s2f)
