import pickle
import math
import torch
import numpy as np
from models.node2vec import Node2Vec
from utils.data_loader import DataLoader


def is_intersect(node1, node2, node3, node4):
    lon1, lat1 = node1['lon'], node1['lat']
    lon2, lat2 = node2['lon'], node2['lat']
    lon3, lat3 = node3['lon'], node3['lat']
    lon4, lat4 = node4['lon'], node4['lat']
    distance1_3 = abs(lon1 - lon3) * 100000 + abs(lat1 - lat3) * 100000
    distance1_4 = abs(lon1 - lon4) * 100000 + abs(lat1 - lat4) * 100000
    distance2_3 = abs(lon2 - lon3) * 100000 + abs(lat2 - lat3) * 100000
    distance2_4 = abs(lon2 - lon4) * 100000 + abs(lat2 - lat4) * 100000
    min_distance = np.min([distance1_3, distance1_4, distance2_3, distance2_4])
    if min_distance == 0:
        return False
    else:
        if np.max([lon1, lon2]) < np.min([lon3, lon4]) or np.max([lon3, lon4]) < np.min([lon1, lon2]):
            return False
        else:
            sort_points = np.sort([lon1, lon2, lon3, lon4])
            left_point, right_point = sort_points[1], sort_points[2]
            if lon1 == lon2:
                value_point1 = [lat1, lat2]
            else:
                value_point1 = [(lat2-lat1)/(lon2-lon1)*(left_point-lon1)+lat1, (lat2-lat1)/(lon2-lon1)*(right_point-lon1)+lat1]
            if lon3 == lon4:
                value_point2 = [lat3, lat4]
            else:
                value_point2 = [(lat4 - lat3) / (lon4 - lon3) * (left_point - lon3) + lat3,
                               (lat4 - lat3) / (lon4 - lon3) * (right_point - lon3) + lat3]
            if np.max(value_point1) < np.min(value_point2) or np.max(value_point2) < np.min(value_point1):
                return False
            else:
                return True


def is_acute(node1, node2, node3, node4):
    lon1, lat1 = node1['lon'], node1['lat']
    lon2, lat2 = node2['lon'], node2['lat']
    lon3, lat3 = node3['lon'], node3['lat']
    lon4, lat4 = node4['lon'], node4['lat']
    distance1_3 = abs(lon1-lon3)*100000 + abs(lat1-lat3)*100000
    distance1_4 = abs(lon1-lon4)*100000 + abs(lat1-lat4)*100000
    distance2_3 = abs(lon2-lon3)*100000 + abs(lat2-lat3)*100000
    distance2_4 = abs(lon2-lon4)*100000 + abs(lat2-lat4)*100000
    min_distance = np.min([distance1_3, distance1_4, distance2_3, distance2_4])
    if min_distance > 0:
        return False
    else:
        if distance1_3 == min_distance:
            x1,y1 = lon2-lon1, lat2-lat1
            x2,y2 = lon4-lon3, lat4-lat3
        if distance1_4 == min_distance:
            x1,y1 = lon2-lon1, lat2-lat1
            x2,y2 = lon3-lon4, lat3-lat4
        if distance2_3 == min_distance:
            x1,y1 = lon1-lon2, lat1-lat2
            x2,y2 = lon4-lon3, lat4-lat3
        if distance2_4 == min_distance:
            x1,y1 = lon1-lon2, lat1-lat2
            x2,y2 = lon3-lon4, lat3-lat4

        vector_1 = [x1, y1]
        vector_2 = [x2, y2]
        unit_vector_1 = vector_1 / np.linalg.norm(vector_1)
        unit_vector_2 = vector_2 / np.linalg.norm(vector_2)
        dot_product = np.dot(unit_vector_1, unit_vector_2)
        angle = np.arccos(dot_product) / math.pi * 180
        if angle < 30:
            return True
        else:
            return False


def is_valid(new_edge, existed_edges, id2node):
    for edge in existed_edges:
        if is_intersect(
                id2node[new_edge['start']], id2node[new_edge['end']],
                id2node[edge['start']], id2node[edge['end']]
        ) or is_acute(
            id2node[new_edge['start']], id2node[new_edge['end']],
            id2node[edge['start']], id2node[edge['end']]
        ):
            return False
    return True


class Node2VecTester():
    def __init__(self, embed_dim, test_data, city):
        self.embed_dim = embed_dim
        self.test_loader = test_data
        self.city = city
        self.embedding = {}
        self.id2node = {}
        self.initialize()

    def initialize(self):
        for k, v in self.test_loader.data[self.city].items():
            for node in v['nodes']:
                ids = node['osmid']
                if ids not in self.id2node:
                    self.id2node[ids] = node

    def test(self, model):
        model.eval()
        right, wrong, total = 0, 0, 0
        if self.embedding == {}:
            self.embedding = pickle.load(open('E:/python-workspace/CityRoadPrediction/data_20200610/node2vec/test/' +
                                              self.city + '_embedding.pkl', 'rb'))
        for ids in self.embedding:
            existed_edges = self.test_loader[ids]['source_edges']
            cand_edges = []
            for sample in self.embedding[ids]:
                start = torch.Tensor(sample['start_embedding'].tolist()).unsqueeze(0)
                end = torch.Tensor(sample['end_embedding'].tolist()).unsqueeze(0)
                output = model(start, end).squeeze(0)
                if output[1] > output[0]:
                    edge = {'start': int(sample['start_id']), 'end': int(sample['end_id']), 'score': float(output[1])}
                    cand_edges.append(edge)
            cand_edges.sort(key=lambda e: e['score'], reverse=True)
            for edge in cand_edges:
                if is_valid(edge, existed_edges, self.id2node):
                    existed_edges.append(edge)
                    if edge in self.test_loader[ids]['target_edges'] or \
                            {'start': edge['end'], 'end': edge['start']} in self.test_loader[ids]['target_edges']:
                        right += 1
                    else:
                        wrong += 1
            total += len(self.test_loader[ids]['target_edges'])
        precision = right / (right + wrong + 1e-9)
        recall = right / (total + 1e-9)
        f1 = 2 * precision * recall / (precision + recall + 1e-9)
        return right, wrong, total, precision, recall, f1


if __name__ == "__main__":

    test = DataLoader('E:/python-workspace/CityRoadPrediction/data_20200610/test/')
    for city in test.data:
        tester = Node2VecTester(embed_dim=50, test_data=test, city=city)
        tester.prepare_test_embedding()
