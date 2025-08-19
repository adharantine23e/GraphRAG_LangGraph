import os 
import re
import json
import pandas as pd
from unidecode import unidecode
from typing import List, Any, Dict, Tuple
from neo4j import GraphDatabase, Session
import logging
from contextlib import contextmanager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def normalized_string(value: str) -> str:
    return "".join(value.split("_")).lower()


def find_relative_type(data_table: pd.DataFrame) -> Dict[str, List[str]]:
    grouped_dict = {}
    for i in range(len(data_table)):
        normalized_value = normalized_string(data_table['relationship_type'][i])
        if normalized_value not in grouped_dict:
            grouped_dict[normalized_value] = []
        grouped_dict[normalized_value].append(data_table['relationship_type'][i])
    return grouped_dict

def replace_relationship(session: Session, relationship_dict: Dict[Any]) -> Tuple[int, List[str], List[str]]:
    index = 0
    key_process = []
    relationship_being_ignored = []
    for key, value in relationship_dict.items():
        if len(value) >1:
            text_to_replace = min(value, key= lambda x:x.count("_"))
            text_to_inflect = max(value, key= lambda x:x.count("_"))
            print("Processing relationship: ", key)
            print("<><><><><><><><><><><><><><><><>")

            replace_dict = find_relationship(session, text_to_replace)
            if len(replace_dict) == 0:
                print("Value being ingnored: ",text_to_replace)
                relationship_being_ignored.append(key)
                continue
            index +=1
            key_process.append(key)
            for item in replace_dict:
                print("Processing item: ", item['projected_id'])
                connect_cypher = f'''
                MATCH (n:`{item['projected_labels'][0]}` {{id: '{item['projected_id']}'}})-[r:{text_to_replace}]->(m:`{item['incoming_labels'][0]}` {{id: "{item['incoming_id']}"}})
                CREATE (n)-[r2:{text_to_inflect}]->(m)
                SET r2 += properties(r)
                WITH r
                DELETE r

            '''
                print("Running the cypher...")
                session.run(connect_cypher)
            print(f"Complete delete relation: {text_to_replace} and create relation: {text_to_inflect}")
            print("###################")
    return index, key_process, relationship_being_ignored

def find_relationship(session: Session, relationship_type):
    default_cypher = '''
    MATCH (n)-[r:{r}]->(k)
    RETURN n.id as projected_id, labels(n) as projected_labels, type(r) as relationship, k.id as incoming_id, labels(k) as incoming_labels
    '''.format(r=relationship_type)
    result = session.run(default_cypher)
    data = []

    for record in result:
        list_value = {}
        list_value['projected_id'] = record['projected_id']
        list_value['projected_labels']= record['projected_labels']
        list_value['relationship'] = record['relationship']
        list_value['incoming_id'] = record['incoming_id']
        list_value['incoming_labels'] = record['incoming_labels']
        data.append(list_value)
    return data

def check_for_Vietnamese(text: str) -> bool:
    vietnamese_pattern = r"[ÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐĨŨƠàáâãèéêìíòóôõùúăđĩũơƯĂẠẢẤẦẨẪẬẮẰẲẴẶẸẺẼỀỀỂưăạảấầẩẫậắằẳẵặẹẻẽềềểỄỆỈỊỌỎỐỒỔỖỘỚỜỞỠỢỤỦỨỪễếệỉịọỏốồổỗộớờởỡợụủứừỬỮỰỲỴÝỶỸửữựỳỵỷỹ]+"

    # Pattern for valid characters (including English letters, digits, and underscores)
    valid_characters_pattern = r"^[a-zA-Z0-9_ÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐĨŨƠàáâãèéêìíòóôõùúăđĩũơƯĂẠẢẤẦẨẪẬẮẰẲẴẶẸẺẼỀỀỂưăạảấầẩẫậắằẳẵặẹẻẽềềểỄỆỈỊỌỎỐỒỔỖỘỚỜỞỠỢỤỦỨỪễếệỉịọỏốồổỗộớờởỡợụủứừỬỮỰỲỴÝỶỸửữựỳỵỷỹ_]+$"
    if re.fullmatch(valid_characters_pattern, text) and re.search(vietnamese_pattern, text):
        return True
    else:
        return False
    
def levenshtein_distance(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        s1, s2 = s2, s1  # Ensure s1 is the longer string
    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[len(s2)]


class GraphPreprocessor:
    def __init__(self, driver: GraphDatabase.driver):
        self.driver = driver
        self.exception_nodes_ascii = None

    @contextmanager
    def get_session(self):
        """Context manager for Neo4j sessions"""
        session = self.driver.session()
        try:
            yield session
        finally:
            session.close()


    def load_list_except_ascii(self, path: str = r"data\exception_underscore_ascii.txt") -> List[str]:
        with open(path, "r") as f:
            contents = f.read()
            return contents.split("\n")

    def find_nodes_(self, session: Session) -> Tuple[List[Dict], List[Dict]]:
        default_cypher ='''
        MATCH (n)
        WHERE n.id CONTAINS "_"
        RETURN collect({`n.id`: n.id}) AS node_list
        '''
        result = session.run(default_cypher)
        record = result.single()

        ascii_nodes = [value for value in record['node_list'] if value['n.id'].isascii()] # English id scattered with Vietnamese id without punctuation (Hairline_Fracture and Rau_Xanh)
        non_ascii_nodes = [value for value in record['node_list'] if not value['n.id'].isascii()] # Vietnamese id (Cơ_Hội)

        return ascii_nodes, non_ascii_nodes

    def batch_find_related_nodes(self, session: Session, _nodes: List[str]) -> List[Dict[str, Any]]:
        list_result = []
        # query = '''
        # MATCH (n1 {id: $node_id})
        # OPTIONAL MATCH (n2)
        # WHERE n2.id = replace(n1.id, "_", " ") AND n1 <> n2
        # RETURN DISTINCT
        #     n1.id AS id,
        #     n2.id AS replacement_of_the_main_id,
        #     labels(n1) AS labels,
        #     labels(n2) AS labels_of_the_replacement
        # '''

        # Change to UNWIND to increase performance
        query = '''
        UNWIND $node_ids AS node_id
        MATCH (n1 {id: node_id})
        OPTIONAL MATCH (n2)
        WHERE n2.id = replace(n1.id, "_", " ") AND n1 <> n2
        RETURN DISTINCT
            n1.id AS id,
            n2.id AS replacement_id,
            labels(n1) AS labels,
            labels(n2) AS replacement_labels
        '''
        
        node_ids = [value['n.id'] for value in _nodes]
        result = session.run(query, node_ids= node_ids)
        result_ids = {record['id']: record for record in result}

        for node in node_ids:
            if node in result_ids:
                record = result_ids[node]
                data = {
                    'id': record['id'],
                    'replacement_of_the_main_id': record['replacement_id'],
                    'labels': record['labels'] or [],
                    'labels_of_the_replacement': record['replacement_labels'] or []
                }
            else:
                data = {
                    'id': node,
                    'replacement_of_the_main_id': None,
                    'labels': [],
                    'labels_of_the_replacement': []
                }
            list_result.append(data)
        return list_result

    def replace_labels(self, session: Session):
        cypher = '''
        CALL db.labels() YIELD label
        WITH lower(replace(replace(label, " ", ""), "_", "")) AS normalized, label
        WITH normalized, collect(label) AS similar_labels
        WHERE size(similar_labels) > 1
        RETURN normalized, similar_labels
        '''
        
        result = session.run(cypher)
        
        for record in result:
            similar_labels = record["similar_labels"]
            
            # Choose the best label (prefer underscore over space)
            target_label = None
            for label in similar_labels:
                if '_' in label:
                    target_label = label
                    break
            
            if not target_label:
                target_label = similar_labels[0].replace(' ', '_')
            
            # Get labels to remove
            labels_to_remove = [label for label in similar_labels if label != target_label]
            
            if labels_to_remove:
                # Build dynamic query
                where_conditions = " OR ".join([f"n:`{label}`" for label in labels_to_remove])
                remove_clauses = ", ".join([f"n:`{label}`" for label in labels_to_remove])
                
                combined_query = f'''
                MATCH (n) 
                WHERE {where_conditions}
                SET n:`{target_label}`
                REMOVE {remove_clauses}
                '''
                
                session.run(combined_query)

    def replace_nodes(self, session: Session, data):
        for value in data:

            default_cypher = f'''MATCH (n)
            WHERE n.id = "{value}"
            WITH n, apoc.text.replace(n.id, "_", " ") AS modified_id
            SET n.id = modified_id
            RETURN n.id
            '''
            # Execute the combined query
            session.run(default_cypher)

    def find_labels(self, session: Session, text: str) -> str:
        default_cypher = f'''
        MATCH (n)
        WHERE n.id = "{text}"
        RETURN labels(n) AS labels
        '''
        resudlt = session.run(default_cypher)
        for record in resudlt:
            return record['labels'][0]

    def delete(self, session: Session, label: str, id: str):
        default_cypher = f'''
        MATCH (n: {label} {{id: "{id}"}})
        DETACH DELETE n
        '''
        session.run(default_cypher)

    def calculate_levenstein_distance(self, session: Session, text: str) -> List[Any]:
        """Return the top 10 most similar nodes to the input text."""
        text_unicoded = unidecode(text).lower().split()
        first_string_to_choose = text_unicoded[0]
        default_cypher = f'''
        MATCH (n)
        WHERE apoc.text.clean(n.id) STARTS WITH "{first_string_to_choose}"
        RETURN n.id as id
        '''
        list_id =[]
        result = session.run(default_cypher)
        ids = [i['id'] for i in result]
        for value in ids:
            if len(value.split()) <= len(text_unicoded) and '"' not in value:
                cypher_check = f'''RETURN apoc.text.levenshteinDistance(apoc.text.clean("{text}"), apoc.text.clean("{value}")) AS output;'''
                output = session.run(cypher_check)
                for record in output:
                    list_id.append({'value': value, "output_score": record["output"]})

        list_id = [value for value in list_id if text != value['value']]
        list_id_sorted = sorted(list_id, key= lambda x: x['output_score'])

        return list_id_sorted[:10]

    def find_relationship(self, session: Session, text: str) -> Dict[str, str]:
        default_cypher = '''
        MATCH (n {id: $node_id})
        OPTIONAL MATCH (n)-[r1]->(target)
        OPTIONAL MATCH (n)<-[r2]-(source)
        
        WITH n, 
             collect(DISTINCT {
                 relationship_type: type(r1),
                 related_node_id: target.id,
                 related_node_labels: labels(target),
                 direction: "outgoing"
             }) AS outgoing,
             collect(DISTINCT {
                 relationship_type: type(r2),
                 related_node_id: source.id,
                 related_node_labels: labels(source),
                 direction: "incoming"
             }) AS incoming
        
        RETURN 
            n.id AS id,
            labels(n) AS labels,
            [rel IN outgoing WHERE rel.related_node_id IS NOT NULL] AS outgoing_relationships,
            [rel IN incoming WHERE rel.related_node_id IS NOT NULL] AS incoming_relationships
        '''

        result = session.run(default_cypher, node_id = text)
        data  = result.single()

        if not data:
            return None
        return {
            'id': data['id'],
            'labels': data['labels'],
            'outgoing_relationships': data['outgoing_relationships'],
            'incoming_relationships': data['incoming_relationships']
        }

    def transfer_labels_batch(self, session: Session, transfer_labels: List[Tuple[List[str], str]]):
        if not transfer_labels:
            return None
        
        for labels_add, target_id in transfer_labels:
            if not labels_add:
                continue

            label_clauses = [f"n:`{label}`" for label in labels_add]
            set_clause = "SET " + ", ".join(label_clauses)

            query = f'''
            MATCH (n {{id:"$target_id"}})
            WHERE NOT ({" OR ".join([f"n:`{label}`" for label in labels_add])})
            {set_clause}
            '''
            session.run(query, target_id = target_id)
        
    def transfer_relations_batch(self, session: Session, transfer_rels: List[Dict]):
        if not transfer_rels:
            return None

        rels_group = {}
        for transfer in transfer_rels:
            rel_type = transfer['relationship_type']
            if rel_type not in rels_group:
                rels_group[rel_type] = []
            rels_group[rel_type].append(transfer)
        
        for rel_type, transfers in rels_group.items():
            clean_rel_type = rel_type.replace("-", "_") if rel_type and "-" in rel_type else rel_type
            outgoing = [t for t in transfers if t['direction'] == 'outgoing']
            incoming = [t for t in transfers if t['direction'] == 'incoming']

            if outgoing:
                cypher_outgoing = f'''
                UNWIND $transfers AS transfer
                MATCH (source {{id: transfer.source_id}})
                MATCH (target {{id: transfer.target_id}})
                MERGE (source)-[:`{clean_rel_type}`]->(target)
                '''
                session.run(cypher_outgoing, transfers = [
                    {
                        'source_id': t['source_id'],
                        'target_id': t['target_id']
                    } for t in outgoing
                ])
            
            # Do the same for incoming relationships
            if incoming:
                cypher_incoming = f'''
                UNWIND $transfers AS transfer
                MATCH (source {{id: transfer.source_id}})
                MATCH (target {{id: transfer.target_id}})
                MERGE (source)-[:`{clean_rel_type}`]->(target)
                '''
                session.run(cypher_incoming, transfers = [
                    {
                        'source_id': t['source_id'],
                        'target_id': t['target_id']
                    } for t in incoming
                ])

    def delete_node_batch(self, session: Session, nodes_list: List[Tuple[str, str]]):
        if not nodes_list:
            pass
        query = '''
        UNWIND $node_ids AS node_id
        MATCH (n {id: node_id.id})
        DETACH DELETE n
        '''
        node_ids = [{'id': node_id} for _, node_id in nodes_list]
        session.run(query, node_ids= node_ids)

    def check_difference_labels(self, value: Dict[str, Any]) ->List[str]:
        differnece_in_labels = [item for item in value['labels'] if item not in value['labels_of_the_replacement']]
        return differnece_in_labels
        
    def assign_labels(self, session: Session, list_labels: List, value_id: str):
        for value in list_labels:
            default_cypher = f'''
            MATCH (n)
            WHERE n.id = "{value_id}" AND NOT n:{value}
            SET n:{value}
            RETURN n
            '''
            # Execute the combined query
            session.run(default_cypher)

    def check_difference_connections(self, result1: Dict[str, Any], result2: Dict[str, Any]):
        all_the_node_in_result1 = [value['related_node_id'] for value in result1['outgoing_relationships']]
        all_the_node_in_result1.extend([value['related_node_id'] for value in result1['incoming_relationships']])
        all_the_node_in_result2 = [value['related_node_id'] for value in result2['outgoing_relationships']]
        all_the_node_in_result2.extend([value['related_node_id'] for value in result2['incoming_relationships']])

        difference_value = list(set(all_the_node_in_result1) - set(all_the_node_in_result2))
        difference_value_filtered = [x for x in difference_value if x is not None]
        return difference_value_filtered

    def connect_relattionship(session: Session, result2: Dict[str, Any], result1: Dict[str, Any], difference_values: List[str]):
        all_relationships_result1 = result1['outgoing_relationships'] + result1['incoming_relationships']
        for diff_val in difference_values:
            for val in all_relationships_result1:
                if diff_val == val['related_node_id']:
                    if val['direction'] == "outgoing":
                        labelA = result2['labels'][0]
                        idA = result2['id']

                        labelB = val['related_node_labels'][0]
                        idB = val['related_node_id']
                        relationship_type = val['relationship_type']

                        if "-" in relationship_type:
                            relationship_type = relationship_type.replace("-", "_")
                        
                        connect_cypher_outward = f'''
                        MATCH (a: {labelA} {{id: "{idA}"}}),  (b: {labelB} {{id: "{idB}"}})
                        MERGE (a) - [r:{relationship_type}] -> (b)
                        RETURN a, b, r
                        '''
                        session.run(connect_cypher_outward)
                    elif val['direction'] == 'incoming':
                        labelA = val['related_node_labels'][0]
                        idA = val['related_node_id']

                        labelB = result2['label'][0]
                        idB = result2['id']
                        relationship_type = val['relationship_type']
                        
                        if "-" in relationship_type:
                            relationship_type = relationship_type.replace("-", "_")
                        connect_cypher_inward = f'''
                        MATCH (a: {labelA} {{id: "{idA}"}}),  (b: {labelB} {{id: "{idB}"}})
                        MERGE (a) - [r:{relationship_type}] -> (b)
                        RETURN a, b, r
                        '''
                        session.run(connect_cypher_inward)
    
    def cacl_missing_rels(self, main_node: Dict[str, Any], replacement_node: Dict[str, Any], replacement_id: str) -> List[Dict[str, Any]]:
        main_connected_nodes = set()
        for rel in main_node['outgoing_relationships'] + main_node['incoming_relationships']:
            if rel['related_node_id']:
                main_connected_nodes.add(rel['related_node_id'])
        
        replacement_connected_nodes = set()
        for rel in replacement_node['outgoing_relationships'] + replacement_node['incoming_relationships']:
            if rel['related_node_id']:
                main_connected_nodes.add(rel['related_node_id'])

        missing_connections = main_connected_nodes - replacement_connected_nodes

        # Relationship transfer
        rels_transfer = []
        for rel in main_node['outgoing_relationships'] + main_node['incoming_relationships']:
            if rel['related_node_id'] in missing_connections:
                if rel['direction'] == 'outgoing':
                    rels_transfer.append({
                        'relationship_type': rel['relationship_type'],
                        'source_id': replacement_id,
                        'target_id': rel['related_node_id'],
                        'direction': 'outgoing'  
                    })
                else:
                    rels_transfer.append({
                        'relationship_type': rel['relationship_type'],
                        'source_id': rel['related_node_id'],
                        'target_id': replacement_id,
                        'direction': 'incoming'  
                    })
        return rels_transfer

    def process_nodes_non_ascii_underscore(self, session: Session):
        logger.info("Processing Vietnamese nodes")

        _, non_ascii_nodes = self.find_nodes_(session= session)
        logger.info(f"Found {len(_)} ASCII nodes and {len(non_ascii_nodes)} non-ASCII nodes")
        
        if not non_ascii_nodes: # Vietnamese id (Cơ_Hội)
            logger.info("No non-ASCII nodes found")
        elif not _: # English id scattered with Vietnamese id without punctuation (Hairline_Fracture and Rau_Xanh)
            logger.info("No ASCII nodes found")
        
        # Since my language is Vietnamese meaning the graph contain id such as "Co_Hoi" and "Cơ_Hội"
        # I have to check the difference between them
        # First seperate the vietnamese id with the others

        # ----------------------------------------------------------------------------------------------
        # Batch processing the nodes with non ascii
        print("The first 3 non ascii nodes for testing are: ", non_ascii_nodes[:3])
        related_nodes = self.batch_find_related_nodes(session= session, _nodes= non_ascii_nodes[:3])
        nodes_replacement = [node for node in related_nodes if node['replacement_of_the_main_id'] is not None]

        label_noascii_transfer = []
        relationship_noascii_transfer = []
        nodes_delete = []

        for node_data in nodes_replacement:
            main_id = node_data['id']
            replacement_id = node_data['replacement_of_the_main_id']
            different_labels = [
                label for label in node_data['labels'] if label not in node_data['labels_of_the_replacement']
            ]
            if different_labels:
                label_noascii_transfer.append((different_labels, replacement_id))
            
            main_relationships = self.find_relationship(session= session, text = main_id)
            if not main_relationships:
                nodes_delete.append(("", main_id))
                continue

            replacement_relationships = self.find_relationship(session= session, text = replacement_id)
            if not replacement_relationships:
                continue

            relationship_noascii_transfer.extend(self.cacl_missing_rels(main_node= main_relationships,
                                                                        replacement_node= replacement_relationships, 
                                                                        replacement_id= replacement_id))
            nodes_delete.append(("", main_id))
        # Execute batch operations
        logger.info("Executing batch label transfers...")
        self.transfer_labels_batch(session, label_noascii_transfer)
        logger.info("Executing batch relationship transfers...")
        self.transfer_relations_batch(session, relationship_noascii_transfer)
        logger.info("Executing batch node deletions...")
        self.delete_node_batch(session, nodes_delete)
        # ----------------------------------------------------------------------------------------------

    def process_nodes__ascii_underscore(self, session: Session):
        self.exception_nodes_ascii = self.load_list_except_ascii()
        if len(self.exception_nodes_ascii) == 0:
            logger.info("No exception nodes found")
        
        ascii_nodes, _ = self.find_nodes_(session= session)
        if not ascii_nodes:
            logger.info("No ASCII nodes found")
            return None
        
        # ----------------------------------------------------------------------------------------------
        # Batch processing the nodes with ascii
        related_nodes = self.batch_find_related_nodes(session = session, _nodes = ascii_nodes)
        nodes_replacement = [node for node in related_nodes if node['replacement_of_the_main_id'] is not None]

        label_ascii_transfer = []
        relationship_ascii_transfer = []
        nodes_delete = []

        for value in nodes_replacement:
            #  Check if the node is in the exception list
            if value['id'] in self.exception_nodes_ascii:
                different_labels = [
                    label for label in value['labels'] if label not in value['labels_of_the_replacement']
                ]
                if different_labels:
                    label_ascii_transfer.append((different_labels, value['replacement_of_the_main_id']))

                main_rels = self.find_relationship(session = session, text= value['id'])
                replacement_rels = self.find_relationship(session = session, text= value['replacement_of_the_main_id'])
                
                if not main_rels or not replacement_rels:
                    nodes_delete.append(("", value['id']))
                    continue

                relationship_ascii_transfer.extend(self.cacl_missing_rels(main_node= main_rels,
                                                                          replacement_node= replacement_rels,
                                                                          replacement_id= value['replacement_of_the_main_id']))
               
                nodes_delete.append(("", value['id']))
                           
            else:
                # This is for nodes like "Tieu_Duong" when strip "_" would become "Tieu Duong" which is still not I want (use levenstein distance to get "Tiểu Dường")
                # Node is not in the exception list
                logger.info(f"Node {value['id']} is not in the exception list")
                main_id = value['id']
                replacement_id = value['replacement_of_the_main_id']

                result1 = self.calculate_levenstein_distance(session= session, text= main_id)

                for i in result1:
                    if i['output_score'] == 0 and "_" not in i['value']:
                        replaced_text = i['value']
                        result2 = self.find_relationship(session= session, text= main_id)
                        result3 = self.find_relationship(session= session, text= replacement_id)
                        
                        if not bool(result2):
                            nodes_delete.append(("", main_id))
                            break 

                        if not bool(result3):
                            continue

                        # Transfer labels to better replacement
                        if value['labels']:
                            label_ascii_transfer.append((value['labels'], replaced_text))

                        relationship_ascii_transfer.extend(self.cacl_missing_rels(  main_node= result2,
                                                                                    replacement_node= result3,
                                                                                    replacement_id= value['replacement_of_the_main_id']))

                    
                        nodes_delete.append(("", value['id']))
                        break
               

        # Execute batch operations
        logger.info("Executing batch label transfers...")
        self.transfer_labels_batch(session, label_ascii_transfer)
        logger.info("Executing batch relationship transfers...")
        self.transfer_relations_batch(session, relationship_ascii_transfer)
        logger.info("Executing batch node deletions...")
        self.delete_node_batch(session, nodes_delete)


    def manual_transfer(self, session: Session,filepath: str = r"data\manual_transfer.json"):
        with open(filepath, "r") as f:
            data = json.load(f)
        nodes_delete = []
        rels_transfer = []
        for value in data:
            main_id = value['value']
            replacement_id = value['value_can_be_replaced']

            main_relationships = self.find_relationship(session= session, text = main_id)
            if not main_relationships:
                nodes_delete.append(("", main_id))
                continue

            replacement_relationships = self.find_relationship(session= session, text = replacement_id)
            if not replacement_relationships:
                continue
            
            rels_transfer.extend(self.cacl_missing_rels(main_node= main_relationships,
                                                        replacement_node= replacement_relationships,
                                                        replacement_id= replacement_id))
            nodes_delete.append(("", main_id))
        self.transfer_relations_batch(session, rels_transfer)
        logger.info("Executing batch node deletions...")
        self.delete_node_batch(session, nodes_delete)


    def graph_preprocessing(self, session: Session):
        logger.info("Processing Vietnamese nodes Starting the full processing...")
        try:
            logger.info("Step 1: Normalize the labels")
            self.replace_labels(session= session)

            logger.info("Step 2: Process the non-ASCII underscore nodes")
            self.process_nodes_non_ascii_underscore(session= session)

            logger.info("Step 3: Process the ASCII underscore nodes")
            self.process_nodes__ascii_underscore(session= session)

            # logger.info("Step 4: Manual transfer")
            # self.manual_transfer(session= session)

        except Exception as e:
            logger.error(f"An error occurred: {e}")


