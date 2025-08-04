import os 
import re
from unidecode import unidecode
from typing import List, Any, Dict
from neo4j import GraphDatabase

def find_nodes_(session: GraphDatabase.driver):
    default_cypher ='''
    MATCH (n)
    WHERE n.id CONTAINS "_"
    RETURN collect({`n.id`: n.id}) AS node_list
    '''
    result = session.run(default_cypher)
    record = result.single()
    return record['node_list'] if record else []

def find_related_nodes_without_ascii(session: GraphDatabase.driver, list_without_ascii: List[str]) -> List[Dict[str, Any]]:
    list_result = []
    query = '''
    MATCH (n1 {id: $node_id})
    OPTIONAL MATCH (n2)
    WHERE n2.id = replace(n1.id, "_", " ") AND n1 <> n2
    RETURN DISTINCT
        n1.id AS id,
        n2.id AS replacement_of_the_main_id,
        labels(n1) AS labels,
        labels(n2) AS labels_of_the_replacement
    '''
    for item in list_without_ascii:
        result = session.run(query, node_id = item['n.id'])
        record = result.data()
        if not record:
            data = {'id': item['n.id'],
                  'replacement_of_the_main_id': None,
                  'labels': [],
                  'labels_of_the_replacement': []}
        else:
            rec = record[0]
            data = {'id': rec['id'],
                    'replacement_of_the_main_id': rec['replacement_of_the_main_id'],
                    'labels': rec['labels'],
                    'labels_of_the_replacement': rec['labels_of_the_replacement']
                    }
        list_result.append(data)
    return list_result

def replace_labels(session: GraphDatabase.driver):
    default_cypher = '''
        CALL db.labels() YIELD label
        WITH lower(replace(replace(label, " ", ""), "_", "")) AS normalizedLabel, label
        WITH collect({normalizedLabel: normalizedLabel, label: label}) AS labels
        UNWIND labels AS label
        WITH label.normalizedLabel AS normalizedLabel, label.label AS label
        WITH normalizedLabel, collect(label) AS labels
        WHERE size(labels) > 1
        RETURN normalizedLabel, labels AS similarLabels
    '''
    result = session.run(default_cypher)

    for record in result:
        similar_labels = record["similarLabels"]
        similar_labels_but_diff = []
        fixed_label = ""

        for label in similar_labels:
            if '_' in label:
                fixed_label = label
            elif " " in label:
                fixed_label = re.sub(" ", "_", label)

        # Create a list of labels excluding the fixed label
        similar_labels_but_diff = [label for label in similar_labels if label != fixed_label]

        # Construct the queries for setting and removing labels
        set_query = f"SET n:{fixed_label}"
        remove_query = "REMOVE " + ", ".join([f"n:`{label}`" for label in similar_labels_but_diff])

        combined_query = f"MATCH (n) WHERE " + " OR ".join([f"n:`{label}`" for label in similar_labels_but_diff]) + f" {set_query} {remove_query}"

        # Execute the combined query
        session.run(combined_query)

def replace_nodes(session, data):
  for value in data:

    default_cypher = f'''MATCH (n)
    WHERE n.id = "{value}"
    WITH n, apoc.text.replace(n.id, "_", " ") AS modified_id
    SET n.id = modified_id
    RETURN n.id
    '''
    # Execute the combined query
    session.run(default_cypher)

def find_labels(session: GraphDatabase.driver, text: str) -> str:
    default_cypher = f'''
    MATCH (n)
    WHERE n.id = "{text}"
    RETURN labels(n) AS labels
    '''
    resudlt = session.run(default_cypher)
    for record in resudlt:
        return record['labels'][0]

def delete(session: GraphDatabase.driver, label: str, id: str):
    default_cypher = f'''
    MATCH (n: {label} {{id: "{id}"}})
    DETACH DELETE n
    '''
    session.run(default_cypher)

def calculate_levenstein_distance(session: GraphDatabase.driver, text: str) -> List[Any]:
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

def find_relationship(session: GraphDatabase.driver, text: str) -> Dict[str, str]:
    default_cypher = '''
    MATCH (n)
    WHERE n.id = "{t}"

    OPTIONAL MATCH (n)-[r1]->(x1)  // Outgoing relationships
    WITH n, COLLECT({{
        relationship_type: TYPE(r1),
        related_node_id: x1.id,
        related_node_labels: LABELS(x1),
        direction: "outgoing"
    }}) AS outgoing_relationships

    OPTIONAL MATCH (n)<-[r2]-(x2)  // Incoming relationships
    WITH n, outgoing_relationships, COLLECT({{
        relationship_type: TYPE(r2),
        related_node_id: x2.id,
        related_node_labels: LABELS(x2),
        direction: "incoming"
    }}) AS incoming_relationships

    RETURN DISTINCT
    n.id AS id,
    labels(n) AS labels,
    outgoing_relationships,
    incoming_relationships
    '''.format(t =text)

    result = session.run(default_cypher)
    data ={}
    for record in result:
        data['id'] = record['id']
        data['labels'] = record['labels']
        data['outgoing_relationships'] = record['outgoing_relationships']
        data['incoming_relationships'] = record['incoming_relationships']
    return data

def check_difference_labels(value: Dict[str, Any]) -> List[str]:
    differnece_in_labels = [item for item in value['labels'] if item not in value['labels_of_the_replacement']]
    return differnece_in_labels
    
def assign_labels(session: GraphDatabase.driver, list_labels: List, value_id: str):
    for value in list_labels:
        default_cypher = f'''
        MATCH (n)
        WHERE n.id = "{value_id}" AND NOT n:{value}
        SET n:{value}
        RETURN n
        '''
        # Execute the combined query
        session.run(default_cypher)

def check_difference_connections(result1: Dict[str, Any], result2: Dict[str, Any]):
    all_the_node_in_result1 = [value['related_node_id'] for value in result1['outgoing_relationships']]
    all_the_node_in_result1.extend([value['related_node_id'] for value in result1['incoming_relationships']])
    all_the_node_in_result2 = [value['related_node_id'] for value in result2['outgoing_relationships']]
    all_the_node_in_result2.extend([value['related_node_id'] for value in result2['incoming_relationships']])

    difference_value = list(set(all_the_node_in_result1) - set(all_the_node_in_result2))
    difference_value_filtered = [x for x in difference_value if x is not None]
    return difference_value_filtered

def connect_relattionship(session: GraphDatabase.driver, example1: Dict[str, Any], result2: Dict[str, Any], difference_values: List[str]):
    all_relationships_result2 = result2['outgoing_relationships'] + result2['incoming_relationships']
    for diff_val in difference_values:
        for val in all_relationships_result2:
            if diff_val == val['related_node_id']:
                if val['direction'] == "outgoing":
                    labelA = example1['labels'][0]
                    idA = example1['id']

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

                    labelB = example1['label'][0]
                    idB = example1['id']
                    relationship_type = val['relationship_type']
                    
                    if "-" in relationship_type:
                        relationship_type = relationship_type.replace("-", "_")
                    connect_cypher_inward = f'''
                    MATCH (a: {labelA} {{id: "{idA}"}}),  (b: {labelB} {{id: "{idB}"}})
                    MERGE (a) - [r:{relationship_type}] -> (b)
                    RETURN a, b, r
                    '''
                    session.run(connect_cypher_inward)
    

if __name__ == "__main__":

    # I do this step since the generated Document from genmma-9b is weird making the graph unordered

    driver = GraphDatabase.driver(
        os.getenv("NEO4J_URI"),
        auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))
    )

    with driver.session() as session:
        # Get all the nodes with character "_" in the id
        nodes_id = find_nodes_(session = session)
        # Since my language is Vietnamese meaning the graph contain id such as "Co_Hoi" and "Cơ_Hội"
        # I have to check the difference between them
        # First seperate the vietnamese id with the others

        list_with_ascii = [value for value in nodes_id if value['n.id'].isascii()] # English id scattered with Vietnamese id without punctuation (Hairline_Fracture and Rau_Xanh)
        list_without_ascii = [value for value in nodes_id if not value['n.id'].isascii()] # Vietnamese id (Cơ_Hội)

        # Deal with list_without_ascii
        for value in list_without_ascii:
            print(f"Processing {value['n.id']}")
            different_labels = check_difference_labels(value)

